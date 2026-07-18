from __future__ import annotations

import csv
import io
from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy import select

from pharma_api.api.dependencies import CSRFProtectedAuth, DBSession, require_permission
from pharma_api.application.analytics.queries import (
    calculate_comparisons,
    calculate_kpi,
    catalog,
    composition,
    drill_down,
    ranking,
    time_series,
)
from pharma_api.application.analytics.service import (
    available_filters,
    cancel_refresh,
    create_goal,
    enforce_analytics_rate_limit,
    freshness,
    list_goals,
    observability,
    queue_refresh,
    update_goal,
)
from pharma_api.application.audit.service import AuditRecord, append_audit_event
from pharma_api.application.auth.types import AuthContext
from pharma_api.core.errors import AppError
from pharma_api.domain.analytics.kpis import KPI_BY_CODE, UNAVAILABLE_KPIS
from pharma_api.infrastructure.cache.redis import get_redis_client
from pharma_api.infrastructure.db.models.analytics import AnalyticsRefreshJob
from pharma_api.schemas.analytics import (
    AnalyticsFilters,
    AnalyticsGoalCreateRequest,
    AnalyticsGoalResponse,
    AnalyticsGoalUpdateRequest,
    AvailableFiltersResponse,
    CompositionItem,
    DrillDownItem,
    FreshnessResponse,
    KpiCatalogResponse,
    KpiComparisonResponse,
    KpiResultResponse,
    RankingItem,
    RefreshJobResponse,
    RefreshRequest,
    TimeSeriesPoint,
    UnavailableKpiResponse,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])
Reader = Annotated[AuthContext, Depends(require_permission("analytics.view"))]
RedisClient = Annotated[Redis, Depends(get_redis_client)]


def _filters(
    from_date: Annotated[date, Query(alias="from")],
    to_date: Annotated[date, Query(alias="to")],
    economic_group_id: UUID | None = None,
    company_id: UUID | None = None,
    branch_id: UUID | None = None,
    product_id: UUID | None = None,
    category_id: UUID | None = None,
    brand_id: UUID | None = None,
    supplier_id: UUID | None = None,
    channel: Annotated[str | None, Query(max_length=60)] = None,
) -> AnalyticsFilters:
    return AnalyticsFilters(
        from_date=from_date,
        to_date=to_date,
        economic_group_id=economic_group_id,
        company_id=company_id,
        branch_id=branch_id,
        product_id=product_id,
        category_id=category_id,
        brand_id=brand_id,
        supplier_id=supplier_id,
        channel=channel,
    )


Filters = Annotated[AnalyticsFilters, Depends(_filters)]


async def _limited(redis: Redis, auth: AuthContext, endpoint: str, maximum: int = 120) -> None:
    await enforce_analytics_rate_limit(
        redis, user_id=auth.user.id, endpoint=endpoint, maximum=maximum
    )


@router.get("/results", response_model=list[KpiResultResponse])
async def get_results(
    filters: Filters,
    session: DBSession,
    redis: RedisClient,
    auth: Reader,
    codes: Annotated[str, Query(min_length=3, max_length=2_000)],
) -> list[KpiResultResponse]:
    requested = list(dict.fromkeys(item.strip() for item in codes.split(",") if item.strip()))
    if not requested or len(requested) > 50:
        raise AppError(
            code="analytics_batch_limit",
            message="Request between 1 and 50 unique KPI codes",
            status_code=422,
        )
    await _limited(redis, auth, "results_batch", maximum=60)
    return [(await calculate_kpi(session, redis, auth, filters, code))[0] for code in requested]


@router.get("/kpis", response_model=list[KpiCatalogResponse | UnavailableKpiResponse])
async def list_kpis(
    auth: Reader,
    category: str | None = None,
    include_unavailable: bool = True,
) -> list[KpiCatalogResponse | UnavailableKpiResponse]:
    definitions = catalog(category)
    if not auth.has_permission("analytics.financial"):
        definitions = [item for item in definitions if item.category != "margin"]
    operational: list[KpiCatalogResponse | UnavailableKpiResponse] = [
        KpiCatalogResponse.model_validate({**definition.as_dict(), "last_updated_at": None})
        for definition in definitions
    ]
    if include_unavailable:
        operational.extend(
            UnavailableKpiResponse.model_validate(item)
            for item in UNAVAILABLE_KPIS
            if category is None or item.category == category
            if item.category != "margin" or auth.has_permission("analytics.financial")
        )
    return operational


@router.get("/kpis/{code}", response_model=KpiCatalogResponse)
async def get_kpi(code: str, auth: Reader) -> KpiCatalogResponse:
    definition = KPI_BY_CODE.get(code)
    if definition is None:
        raise AppError(code="kpi_not_found", message="KPI not found", status_code=404)
    if definition.category == "margin" and not auth.has_permission("analytics.financial"):
        raise AppError(
            code="financial_analytics_forbidden", message="Permission denied", status_code=403
        )
    return KpiCatalogResponse.model_validate({**definition.as_dict(), "last_updated_at": None})


@router.get("/results/{code}", response_model=KpiResultResponse)
async def get_result(
    code: str,
    filters: Filters,
    response: Response,
    session: DBSession,
    redis: RedisClient,
    auth: Reader,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> KpiResultResponse | Response:
    await _limited(redis, auth, "result")
    result, identity = await calculate_kpi(session, redis, auth, filters, code)
    etag = f'"{identity}"'
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=60"
    return result


@router.get("/comparisons/{code}", response_model=KpiComparisonResponse)
async def compare_result(
    code: str,
    filters: Filters,
    session: DBSession,
    redis: RedisClient,
    auth: Reader,
) -> KpiComparisonResponse:
    await _limited(redis, auth, "comparison")
    return await calculate_comparisons(session, redis, auth, filters, code)


@router.get("/timeseries/{code}", response_model=list[TimeSeriesPoint])
async def get_time_series(
    code: str, filters: Filters, session: DBSession, redis: RedisClient, auth: Reader
) -> list[TimeSeriesPoint]:
    await _limited(redis, auth, "timeseries")
    return await time_series(session, auth, filters, code)


@router.get("/rankings/{code}", response_model=list[RankingItem])
async def get_ranking(
    code: str,
    filters: Filters,
    session: DBSession,
    redis: RedisClient,
    auth: Reader,
    dimension: Annotated[str, Query(pattern="^(product|category|supplier|channel)$")] = "product",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[RankingItem]:
    await _limited(redis, auth, "ranking")
    return await ranking(session, auth, filters, code, dimension, limit)


@router.get("/composition/{code}", response_model=list[CompositionItem])
async def get_composition(
    code: str,
    filters: Filters,
    session: DBSession,
    redis: RedisClient,
    auth: Reader,
    dimension: Annotated[str, Query(pattern="^(product|category|supplier|channel)$")] = "category",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[CompositionItem]:
    await _limited(redis, auth, "composition")
    return await composition(session, auth, filters, code, dimension, limit)


@router.get("/drilldown/{code}", response_model=list[DrillDownItem])
async def get_drilldown(
    code: str,
    filters: Filters,
    request: Request,
    session: DBSession,
    redis: RedisClient,
    auth: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> list[DrillDownItem]:
    await _limited(redis, auth, "drilldown", maximum=60)
    rows = await drill_down(session, auth, filters, code, limit, offset)
    await append_audit_event(
        session,
        AuditRecord(
            action="analytics.detail.accessed",
            category="analytics_security",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=auth.tenant_id,
            company_id=filters.company_id,
            branch_id=filters.branch_id,
            resource_type="kpi",
            resource_id=code,
            correlation_id=getattr(request.state, "correlation_id", None),
            metadata={"limit": limit, "offset": offset},
        ),
    )
    return rows


@router.get("/goals", response_model=list[AnalyticsGoalResponse])
async def get_goals(session: DBSession, auth: Reader) -> list[AnalyticsGoalResponse]:
    return [AnalyticsGoalResponse.model_validate(goal) for goal in await list_goals(session, auth)]


@router.post("/goals", response_model=AnalyticsGoalResponse, status_code=status.HTTP_201_CREATED)
async def add_goal(
    payload: AnalyticsGoalCreateRequest,
    request: Request,
    session: DBSession,
    auth: CSRFProtectedAuth,
) -> AnalyticsGoalResponse:
    goal = await create_goal(session, auth, payload, getattr(request.state, "correlation_id", None))
    return AnalyticsGoalResponse.model_validate(goal)


@router.patch("/goals/{goal_id}", response_model=AnalyticsGoalResponse)
async def edit_goal(
    goal_id: UUID,
    payload: AnalyticsGoalUpdateRequest,
    request: Request,
    session: DBSession,
    auth: CSRFProtectedAuth,
) -> AnalyticsGoalResponse:
    goal = await update_goal(
        session, auth, goal_id, payload, getattr(request.state, "correlation_id", None)
    )
    return AnalyticsGoalResponse.model_validate(goal)


@router.get("/filters", response_model=AvailableFiltersResponse)
async def get_filters(session: DBSession, auth: Reader) -> AvailableFiltersResponse:
    return await available_filters(session, auth)


@router.get("/dimensions", response_model=dict[str, list[dict[str, str]]])
async def get_dimensions(session: DBSession, auth: Reader) -> dict[str, list[dict[str, str]]]:
    visible = await available_filters(session, auth)
    return {
        "economic_group": [
            {"key": item["id"], "label": item["label"]} for item in visible.economic_groups
        ],
        "company": [{"key": item["id"], "label": item["label"]} for item in visible.companies],
        "branch": [{"key": item["id"], "label": item["label"]} for item in visible.branches],
        "product": [{"key": item["id"], "label": item["label"]} for item in visible.products],
        "category": [{"key": item["id"], "label": item["label"]} for item in visible.categories],
        "brand": [{"key": item["id"], "label": item["label"]} for item in visible.brands],
        "supplier": [{"key": item["id"], "label": item["label"]} for item in visible.suppliers],
        "channel": [{"key": item, "label": item} for item in visible.channels],
    }


@router.get("/freshness", response_model=FreshnessResponse)
async def get_freshness(session: DBSession, auth: Reader) -> FreshnessResponse:
    return await freshness(session, auth)


@router.get("/quality", response_model=list[KpiResultResponse])
async def get_quality(
    filters: Filters, session: DBSession, redis: RedisClient, auth: Reader
) -> list[KpiResultResponse]:
    codes = (
        "operations.data_freshness",
        "operations.completeness",
        "operations.rejection_rate",
        "operations.duplicate_rate",
        "operations.consistency",
    )
    return [(await calculate_kpi(session, redis, auth, filters, code))[0] for code in codes]


@router.get("/observability", response_model=dict[str, int | float | None])
async def get_observability(
    session: DBSession, redis: RedisClient, auth: Reader
) -> dict[str, int | float | None]:
    return await observability(session, auth, redis)


def _safe_csv(value: Any) -> str:
    rendered = "" if value is None else str(value)
    if rendered.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{rendered}"
    return rendered


@router.get("/export.csv")
async def export_results(
    filters: Filters,
    request: Request,
    session: DBSession,
    redis: RedisClient,
    auth: Reader,
    codes: Annotated[str, Query(min_length=3, max_length=2_000)] = "sales.net_revenue",
) -> StreamingResponse:
    if not auth.has_permission("analytics.export"):
        raise AppError(
            code="analytics_export_forbidden", message="Export permission required", status_code=403
        )
    requested = list(dict.fromkeys(item.strip() for item in codes.split(",") if item.strip()))
    if len(requested) > 50:
        raise AppError(
            code="export_limit", message="At most 50 KPIs may be exported", status_code=422
        )
    await _limited(redis, auth, "export", maximum=20)
    results = [(await calculate_kpi(session, redis, auth, filters, code))[0] for code in requested]
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "kpi_code",
            "name",
            "period_start",
            "period_end",
            "value",
            "unit",
            "comparison",
            "variation_percent",
            "formula_version",
            "data_version",
            "freshness_at",
        ]
    )
    for item in results:
        writer.writerow(
            [
                _safe_csv(item.code),
                _safe_csv(item.name),
                item.period_start,
                item.period_end,
                item.value,
                _safe_csv(item.unit),
                item.comparison_value,
                item.percentage_variation,
                item.formula_version,
                item.data_version,
                item.freshness_at,
            ]
        )
    await append_audit_event(
        session,
        AuditRecord(
            action="analytics.export.created",
            category="analytics_security",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=auth.tenant_id,
            company_id=filters.company_id,
            branch_id=filters.branch_id,
            resource_type="analytics_export",
            correlation_id=getattr(request.state, "correlation_id", None),
            metadata={"kpis": requested, "format": "csv"},
        ),
    )
    payload = output.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        iter((payload,)),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="analytics-export.csv"'},
    )


@router.post("/refresh", response_model=RefreshJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_refresh(
    payload: RefreshRequest,
    request: Request,
    session: DBSession,
    auth: CSRFProtectedAuth,
) -> RefreshJobResponse:
    job = await queue_refresh(
        session, auth, payload, getattr(request.state, "correlation_id", None)
    )
    return RefreshJobResponse.model_validate(job)


@router.get("/refresh/{job_id}", response_model=RefreshJobResponse)
async def get_refresh(job_id: UUID, session: DBSession, auth: Reader) -> RefreshJobResponse:
    job = await session.scalar(select(AnalyticsRefreshJob).where(AnalyticsRefreshJob.id == job_id))
    if job is None or job.tenant_id != auth.tenant_id:
        raise AppError(code="not_found", message="Refresh job not found", status_code=404)
    return RefreshJobResponse.model_validate(job)


@router.post("/refresh/{job_id}/cancel", response_model=RefreshJobResponse)
async def stop_refresh(
    job_id: UUID,
    request: Request,
    session: DBSession,
    auth: CSRFProtectedAuth,
) -> RefreshJobResponse:
    job = await cancel_refresh(
        session, auth, job_id, getattr(request.state, "correlation_id", None)
    )
    return RefreshJobResponse.model_validate(job)
