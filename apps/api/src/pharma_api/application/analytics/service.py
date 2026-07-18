from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.analytics.queries import cache_metric_key
from pharma_api.application.analytics.scopes import (
    analytics_visibility_filter,
    require_analytics_scope,
)
from pharma_api.application.audit.service import AuditRecord, append_audit_event
from pharma_api.application.auth.types import AuthContext
from pharma_api.core.errors import AppError
from pharma_api.domain.analytics.kpis import KPI_BY_CODE
from pharma_api.infrastructure.db.models.analytics import (
    AnalyticsDailyAggregate,
    AnalyticsDataVersion,
    AnalyticsDimension,
    AnalyticsFact,
    AnalyticsGoal,
    AnalyticsGoalHistory,
    AnalyticsRefreshJob,
)
from pharma_api.infrastructure.db.models.integration import ImportBatch
from pharma_api.infrastructure.db.models.organizations import Membership
from pharma_api.schemas.analytics import (
    AnalyticsGoalCreateRequest,
    AnalyticsGoalUpdateRequest,
    AvailableFiltersResponse,
    FreshnessResponse,
    RefreshRequest,
)


async def enforce_analytics_rate_limit(
    redis: Redis, *, user_id: UUID, endpoint: str, maximum: int = 120
) -> None:
    now = datetime.now(UTC)
    bucket = int(now.timestamp()) // 60
    key = f"rate:analytics:{user_id}:{endpoint}:{bucket}"
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 90)
    except RedisError as exc:
        raise AppError(
            code="analytics_rate_limit_unavailable",
            message="Analytics rate limiting is temporarily unavailable",
            status_code=503,
        ) from exc
    if count > maximum:
        raise AppError(
            code="analytics_rate_limit_exceeded",
            message="Too many analytical requests",
            status_code=429,
        )


def _goal_snapshot(goal: AnalyticsGoal) -> dict[str, Any]:
    return {
        "company_id": str(goal.company_id) if goal.company_id else None,
        "branch_id": str(goal.branch_id) if goal.branch_id else None,
        "kpi_code": goal.kpi_code,
        "period_start": goal.period_start.isoformat(),
        "period_end": goal.period_end.isoformat(),
        "target_value": str(goal.target_value) if goal.target_value is not None else None,
        "lower_value": str(goal.lower_value) if goal.lower_value is not None else None,
        "upper_value": str(goal.upper_value) if goal.upper_value is not None else None,
        "direction": goal.direction,
        "owner_user_id": str(goal.owner_user_id),
        "note": goal.note,
        "active": goal.active,
        "version": goal.version,
    }


async def _validate_goal_owner(session: AsyncSession, tenant_id: UUID, owner_user_id: UUID) -> None:
    owner = await session.scalar(
        select(Membership.id).where(
            Membership.tenant_id == tenant_id,
            Membership.user_id == owner_user_id,
            Membership.status == "active",
        )
    )
    if owner is None:
        raise AppError(
            code="analytics_goal_owner_invalid",
            message="Goal owner must be an active tenant member",
            status_code=422,
        )


async def list_goals(session: AsyncSession, auth: AuthContext) -> list[AnalyticsGoal]:
    return list(
        (
            await session.scalars(
                select(AnalyticsGoal)
                .where(
                    analytics_visibility_filter(
                        auth,
                        "analytics.view",
                        AnalyticsGoal.tenant_id,
                        AnalyticsGoal.company_id,
                        AnalyticsGoal.branch_id,
                    )
                )
                .order_by(AnalyticsGoal.period_start.desc(), AnalyticsGoal.kpi_code)
                .limit(500)
            )
        ).all()
    )


async def create_goal(
    session: AsyncSession,
    auth: AuthContext,
    payload: AnalyticsGoalCreateRequest,
    correlation_id: str | None,
) -> AnalyticsGoal:
    if auth.tenant_id is None:
        raise AppError(code="tenant_context_required", message="Select a tenant", status_code=409)
    if payload.kpi_code not in KPI_BY_CODE:
        raise AppError(code="kpi_not_found", message="KPI not found", status_code=404)
    if KPI_BY_CODE[payload.kpi_code].category == "margin" and not auth.has_permission(
        "analytics.financial"
    ):
        raise AppError(
            code="financial_analytics_forbidden",
            message="Financial analytics permission is required",
            status_code=403,
        )
    require_analytics_scope(
        auth,
        "analytics.goals.manage",
        company_id=payload.company_id,
        branch_id=payload.branch_id,
    )
    await _validate_goal_owner(session, auth.tenant_id, payload.owner_user_id)
    goal = AnalyticsGoal(
        tenant_id=auth.tenant_id,
        **payload.model_dump(),
    )
    session.add(goal)
    await session.flush()
    session.add(
        AnalyticsGoalHistory(
            tenant_id=auth.tenant_id,
            goal_id=goal.id,
            version=goal.version,
            snapshot=_goal_snapshot(goal),
            changed_by_user_id=auth.user.id,
            change_reason="created",
            changed_at=datetime.now(UTC),
        )
    )
    await append_audit_event(
        session,
        AuditRecord(
            action="analytics.goal.created",
            category="analytics",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=auth.tenant_id,
            company_id=goal.company_id,
            branch_id=goal.branch_id,
            resource_type="analytics_goal",
            resource_id=str(goal.id),
            correlation_id=correlation_id,
            changed_fields=list(payload.model_fields_set),
        ),
    )
    return goal


async def update_goal(
    session: AsyncSession,
    auth: AuthContext,
    goal_id: UUID,
    payload: AnalyticsGoalUpdateRequest,
    correlation_id: str | None,
) -> AnalyticsGoal:
    goal = await session.scalar(
        select(AnalyticsGoal).where(AnalyticsGoal.id == goal_id).with_for_update()
    )
    if goal is None:
        raise AppError(code="not_found", message="Goal not found", status_code=404)
    require_analytics_scope(
        auth,
        "analytics.goals.manage",
        company_id=goal.company_id,
        branch_id=goal.branch_id,
    )
    if goal.version != payload.expected_version:
        raise AppError(code="version_conflict", message="Goal was modified", status_code=409)
    changes = payload.model_dump(exclude={"expected_version", "change_reason"}, exclude_unset=True)
    for field, value in changes.items():
        setattr(goal, field, value)
    if goal.target_value is None and goal.lower_value is None and goal.upper_value is None:
        raise AppError(
            code="analytics_goal_target_required",
            message="A target value or interval is required",
            status_code=422,
        )
    if (
        goal.lower_value is not None
        and goal.upper_value is not None
        and goal.upper_value < goal.lower_value
    ):
        raise AppError(
            code="analytics_goal_range_invalid",
            message="Goal upper value must not be below lower value",
            status_code=422,
        )
    await _validate_goal_owner(session, goal.tenant_id, goal.owner_user_id)
    goal.version += 1
    session.add(
        AnalyticsGoalHistory(
            tenant_id=goal.tenant_id,
            goal_id=goal.id,
            version=goal.version,
            snapshot=_goal_snapshot(goal),
            changed_by_user_id=auth.user.id,
            change_reason=payload.change_reason,
            changed_at=datetime.now(UTC),
        )
    )
    await append_audit_event(
        session,
        AuditRecord(
            action="analytics.goal.updated",
            category="analytics",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=goal.tenant_id,
            company_id=goal.company_id,
            branch_id=goal.branch_id,
            resource_type="analytics_goal",
            resource_id=str(goal.id),
            correlation_id=correlation_id,
            changed_fields=list(changes),
            justification=payload.change_reason,
        ),
    )
    return goal


async def queue_refresh(
    session: AsyncSession,
    auth: AuthContext,
    payload: RefreshRequest,
    correlation_id: str | None,
) -> AnalyticsRefreshJob:
    if auth.tenant_id is None:
        raise AppError(code="tenant_context_required", message="Select a tenant", status_code=409)
    permission = "analytics.backfill" if payload.mode == "backfill" else "analytics.recompute"
    if not auth.has_tenant_wide_permission(permission, auth.tenant_id):
        raise AppError(
            code="tenant_wide_permission_required",
            message="A tenant-wide analytical permission is required",
            status_code=403,
        )
    existing = await session.scalar(
        select(AnalyticsRefreshJob).where(
            AnalyticsRefreshJob.tenant_id == auth.tenant_id,
            AnalyticsRefreshJob.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        return existing
    version = await session.scalar(
        select(AnalyticsDataVersion).where(AnalyticsDataVersion.tenant_id == auth.tenant_id)
    )
    job = AnalyticsRefreshJob(
        tenant_id=auth.tenant_id,
        trigger_type=payload.mode,
        idempotency_key=payload.idempotency_key,
        state="queued",
        window_start=datetime.combine(payload.from_date, time.min, tzinfo=UTC),
        window_end=datetime.combine(payload.to_date + timedelta(days=1), time.min, tzinfo=UTC),
        watermark_before=version.watermark if version else None,
        checkpoint={"step": "queued", "correlation_id": correlation_id},
        metrics={},
        requested_by_user_id=auth.user.id,
    )
    session.add(job)
    await session.flush()
    job_id = job.id
    await append_audit_event(
        session,
        AuditRecord(
            action=f"analytics.{payload.mode}.queued",
            category="analytics",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=auth.tenant_id,
            resource_type="analytics_refresh_job",
            resource_id=str(job.id),
            correlation_id=correlation_id,
            metadata={"from": payload.from_date.isoformat(), "to": payload.to_date.isoformat()},
        ),
    )
    await session.commit()
    # The primary key is generated client-side; avoid a post-commit refresh after
    # transaction-local RLS context has been cleared.
    from pharma_api.infrastructure.analytics.tasks import refresh_analytics

    refresh_analytics.send(str(job_id), str(job.tenant_id))
    return job


async def cancel_refresh(
    session: AsyncSession, auth: AuthContext, job_id: UUID, correlation_id: str | None
) -> AnalyticsRefreshJob:
    job = await session.scalar(
        select(AnalyticsRefreshJob).where(AnalyticsRefreshJob.id == job_id).with_for_update()
    )
    if job is None:
        raise AppError(code="not_found", message="Refresh job not found", status_code=404)
    if auth.tenant_id != job.tenant_id or not auth.has_tenant_wide_permission(
        "analytics.recompute", job.tenant_id
    ):
        raise AppError(code="forbidden", message="Permission denied", status_code=403)
    if job.state in {"completed", "failed", "cancelled"}:
        return job
    job.cancel_requested_at = datetime.now(UTC)
    job.version += 1
    await append_audit_event(
        session,
        AuditRecord(
            action="analytics.refresh.cancel_requested",
            category="analytics",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=job.tenant_id,
            resource_type="analytics_refresh_job",
            resource_id=str(job.id),
            correlation_id=correlation_id,
        ),
    )
    return job


async def available_filters(session: AsyncSession, auth: AuthContext) -> AvailableFiltersResponse:
    visible = analytics_visibility_filter(
        auth,
        "analytics.view",
        AnalyticsDailyAggregate.tenant_id,
        AnalyticsDailyAggregate.company_id,
        AnalyticsDailyAggregate.branch_id,
    )
    rows = list(
        (
            await session.execute(
                select(
                    AnalyticsDailyAggregate.company_id,
                    AnalyticsDailyAggregate.branch_id,
                    AnalyticsDailyAggregate.product_id,
                    AnalyticsDailyAggregate.category_id,
                    AnalyticsDailyAggregate.supplier_id,
                    AnalyticsDailyAggregate.grain,
                    AnalyticsDailyAggregate.dimension_value,
                )
                .where(visible)
                .distinct()
                .limit(5_000)
            )
        ).all()
    )
    ids: dict[str, set[str]] = {
        "economic_group": set(),
        "company": set(),
        "branch": set(),
        "product": set(),
        "category": set(),
        "brand": set(),
        "supplier": set(),
    }
    channels: set[str] = set()
    for company, branch, product, category, supplier, grain, value in rows:
        for key, item in (
            ("company", company),
            ("branch", branch),
            ("product", product),
            ("category", category),
            ("supplier", supplier),
        ):
            if item is not None:
                ids[key].add(str(item))
        if grain == "channel" and value:
            channels.add(value)
    labels: dict[tuple[str, str], str] = {}
    dimensions: list[AnalyticsDimension] = []
    if auth.tenant_id is not None:
        dimensions = list(
            (
                await session.scalars(
                    select(AnalyticsDimension).where(
                        AnalyticsDimension.tenant_id == auth.tenant_id,
                        AnalyticsDimension.current.is_(True),
                    )
                )
            ).all()
        )
        labels = {(item.dimension_type, item.natural_key): item.label for item in dimensions}
        visible_companies = ids["company"]
        visible_products = ids["product"]
        for item in dimensions:
            if (
                item.dimension_type == "company"
                and item.natural_key in visible_companies
                and item.parent_natural_key
            ):
                ids["economic_group"].add(item.parent_natural_key)
            if item.dimension_type == "product" and item.natural_key in visible_products:
                brand_id = item.attributes.get("brand_id")
                if brand_id:
                    ids["brand"].add(str(brand_id))
    bounds = (
        await session.execute(
            select(
                func.min(AnalyticsDailyAggregate.date_value),
                func.max(AnalyticsDailyAggregate.date_value),
            ).where(visible)
        )
    ).one()

    def options(kind: str) -> list[dict[str, str]]:
        return [{"id": item, "label": labels.get((kind, item), item)} for item in sorted(ids[kind])]

    return AvailableFiltersResponse(
        economic_groups=options("economic_group"),
        companies=options("company"),
        branches=options("branch"),
        products=options("product"),
        categories=options("category"),
        brands=options("brand"),
        suppliers=options("supplier"),
        channels=sorted(channels),
        minimum_date=bounds[0],
        maximum_date=bounds[1],
    )


async def freshness(session: AsyncSession, auth: AuthContext) -> FreshnessResponse:
    if auth.tenant_id is None:
        raise AppError(code="tenant_context_required", message="Select a tenant", status_code=409)
    row = await session.scalar(
        select(AnalyticsDataVersion).where(AnalyticsDataVersion.tenant_id == auth.tenant_id)
    )
    if row is None:
        return FreshnessResponse(
            data_version=0,
            watermark=None,
            freshness_at=None,
            lag_seconds=None,
            quality_score=None,
            last_refresh_job_id=None,
        )
    lag = (
        max(int((datetime.now(UTC) - row.freshness_at).total_seconds()), 0)
        if row.freshness_at
        else None
    )
    return FreshnessResponse(
        data_version=row.current_version,
        watermark=row.watermark,
        freshness_at=row.freshness_at,
        lag_seconds=lag,
        quality_score=row.quality_score,
        last_refresh_job_id=row.last_refresh_job_id,
    )


async def observability(
    session: AsyncSession, auth: AuthContext, redis: Redis
) -> dict[str, int | float | None]:
    if auth.tenant_id is None:
        raise AppError(code="tenant_context_required", message="Select a tenant", status_code=409)
    tenant_wide = auth.has_tenant_wide_permission("analytics.view", auth.tenant_id)
    job_visibility: list[Any] = [AnalyticsRefreshJob.tenant_id == auth.tenant_id]
    if not tenant_wide:
        visible_batches = select(ImportBatch.id).where(
            analytics_visibility_filter(
                auth,
                "analytics.view",
                ImportBatch.tenant_id,
                ImportBatch.company_id,
                ImportBatch.branch_id,
            )
        )
        job_visibility.append(AnalyticsRefreshJob.source_batch_id.in_(visible_batches))
    state_rows = (
        await session.execute(
            select(AnalyticsRefreshJob.state, func.count(AnalyticsRefreshJob.id))
            .where(*job_visibility)
            .group_by(AnalyticsRefreshJob.state)
        )
    ).all()
    states: dict[str, int] = {state: int(count) for state, count in state_rows}
    duration = await session.scalar(
        select(func.avg(AnalyticsRefreshJob.completed_at - AnalyticsRefreshJob.started_at)).where(
            *job_visibility,
            AnalyticsRefreshJob.state == "completed",
        )
    )
    facts = await session.scalar(
        select(func.count(AnalyticsFact.id)).where(
            analytics_visibility_filter(
                auth,
                "analytics.view",
                AnalyticsFact.tenant_id,
                AnalyticsFact.company_id,
                AnalyticsFact.branch_id,
            )
        )
    )
    aggregates = await session.scalar(
        select(func.count(AnalyticsDailyAggregate.id)).where(
            analytics_visibility_filter(
                auth,
                "analytics.view",
                AnalyticsDailyAggregate.tenant_id,
                AnalyticsDailyAggregate.company_id,
                AnalyticsDailyAggregate.branch_id,
            )
        )
    )
    trigger_rows = (
        await session.execute(
            select(AnalyticsRefreshJob.trigger_type, func.count(AnalyticsRefreshJob.id))
            .where(
                *job_visibility,
                AnalyticsRefreshJob.trigger_type.in_(("backfill", "recompute")),
            )
            .group_by(AnalyticsRefreshJob.trigger_type)
        )
    ).all()
    triggers = {trigger: int(count) for trigger, count in trigger_rows}
    version = await session.scalar(
        select(AnalyticsDataVersion).where(AnalyticsDataVersion.tenant_id == auth.tenant_id)
    )
    try:
        cache_metrics = await redis.hgetall(cache_metric_key(auth))
    except RedisError as exc:
        raise AppError(
            code="analytics_cache_unavailable",
            message="Analytical cache telemetry is temporarily unavailable",
            status_code=503,
        ) from exc
    cache_requests = int(cache_metrics.get("requests", 0))
    cache_hits = int(cache_metrics.get("hits", 0))
    table_sizes: tuple[int | None, int | None] = (None, None)
    if tenant_wide:
        size_row = (
            await session.execute(
                text(
                    "SELECT pg_total_relation_size('analytics_facts'),"
                    "pg_total_relation_size('analytics_daily_aggregates')"
                )
            )
        ).one()
        table_sizes = (int(size_row[0]), int(size_row[1]))
    return {
        "refresh_queued": int(states.get("queued", 0)),
        "refresh_running": int(states.get("running", 0)),
        "refresh_completed": int(states.get("completed", 0)),
        "refresh_failed": int(states.get("failed", 0)),
        "refresh_cancelled": int(states.get("cancelled", 0)),
        "facts": int(facts or 0),
        "aggregates": int(aggregates or 0),
        "cache_requests": cache_requests,
        "cache_hits": cache_hits,
        "cache_misses": max(cache_requests - cache_hits, 0),
        "cache_hit_rate": (cache_hits / cache_requests) if cache_requests else None,
        "backfills": triggers.get("backfill", 0),
        "recomputations": triggers.get("recompute", 0),
        "average_job_duration_seconds": duration.total_seconds() if duration else None,
        "data_version": version.current_version if version else 0,
        "quality_score": float(version.quality_score)
        if version and version.quality_score
        else None,
        "analytical_lag_seconds": (
            max(int((datetime.now(UTC) - version.freshness_at).total_seconds()), 0)
            if version and version.freshness_at
            else None
        ),
        "facts_table_bytes": int(table_sizes[0]) if table_sizes[0] is not None else None,
        "aggregates_table_bytes": int(table_sizes[1]) if table_sizes[1] is not None else None,
    }
