from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import Uuid, and_, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.analytics.scopes import (
    analytics_visibility_filter,
    require_analytics_scope,
)
from pharma_api.application.auth.types import AuthContext
from pharma_api.core.errors import AppError
from pharma_api.domain.analytics.kpis import (
    KPI_BY_CODE,
    KPI_CATALOG,
    KpiDefinition,
    evaluate_formula,
)
from pharma_api.infrastructure.db.models.analytics import (
    AnalyticsDailyAggregate,
    AnalyticsDataVersion,
    AnalyticsDimension,
    AnalyticsFact,
    AnalyticsGoal,
    AnalyticsKpiResult,
    AnalyticsLineage,
)
from pharma_api.schemas.analytics import (
    AnalyticsFilters,
    CompositionItem,
    DrillDownItem,
    KpiComparisonResponse,
    KpiResultResponse,
    RankingItem,
    TimeSeriesPoint,
)

_CACHE_TTL_SECONDS = 300
_MAX_AGGREGATE_ROWS = 10_000
_POINT_IN_TIME_MEASURES = frozenset(
    {
        "inventory_on_hand",
        "inventory_available",
        "inventory_reserved",
        "inventory_in_transit",
        "inventory_retail_value",
        "inventory_cost_value",
        "scoped_inventory_value",
        "negative_stock_products",
        "zero_stock_products",
        "active_products",
    }
)
DERIVED_MEASURES = frozenset(
    {
        "active_days",
        "active_hours",
        "average_daily_units",
        "average_inventory_cost",
        "gross_profit",
        "network_net_revenue",
        "scoped_net_revenue",
        "scoped_gross_profit",
        "units_available_for_sale",
        "freshness_seconds",
        "sold_product_count",
        "top10_revenue",
        "demand_stddev",
        "low_cover_products",
        "excess_stock_products",
        "slow_moving_products",
        "no_sale_products",
        "active_supplier_count",
        "top_supplier_value",
        "top5_supplier_value",
        "supplier_product_count",
        "average_price",
        "price_stddev",
        "cache_hits",
        "cache_requests",
    }
)


def _decimal(value: object) -> Decimal:
    if isinstance(value, bytes):
        value = value.decode("ascii")
    return Decimal(str(value or 0))


def _cache_identity(
    tenant_id: UUID,
    auth: AuthContext,
    filters: AnalyticsFilters,
    definition: KpiDefinition,
    version: int,
) -> str:
    payload = {
        "tenant": str(tenant_id),
        "grants": sorted(
            f"{grant.key}:{grant.scope}:{grant.company_id}:{grant.branch_id}"
            for grant in auth.grants_for("analytics.view")
        ),
        "filters": filters.model_dump(mode="json"),
        "kpi": definition.code,
        "formula_version": definition.version,
        "data_version": version,
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def cache_metric_key(auth: AuthContext) -> str:
    grants = sorted(
        f"{grant.key}:{grant.scope}:{grant.company_id}:{grant.branch_id}"
        for grant in auth.grants_for("analytics.view")
    )
    digest = sha256("|".join(grants).encode()).hexdigest()[:24]
    return f"analytics:cache-metrics:{auth.tenant_id}:{digest}"


def _validate_access(
    auth: AuthContext, definition: KpiDefinition, filters: AnalyticsFilters
) -> None:
    if definition.category == "margin" and not auth.has_permission("analytics.financial"):
        raise AppError(
            code="financial_analytics_forbidden",
            message="Financial analytics permission is required",
            status_code=403,
        )
    if filters.company_id is not None:
        require_analytics_scope(
            auth,
            "analytics.view",
            company_id=filters.company_id,
            branch_id=filters.branch_id,
        )


def _aggregate_filters(auth: AuthContext, filters: AnalyticsFilters) -> list[Any]:
    clauses = _organizational_filters(auth, filters)
    for column, value in (
        (AnalyticsDailyAggregate.product_id, filters.product_id),
        (AnalyticsDailyAggregate.category_id, filters.category_id),
        (AnalyticsDailyAggregate.supplier_id, filters.supplier_id),
    ):
        if value is not None:
            clauses.append(column == value)
    if filters.channel is not None:
        clauses.extend(
            [
                AnalyticsDailyAggregate.grain == "channel",
                AnalyticsDailyAggregate.dimension_value == filters.channel,
            ]
        )
    if filters.brand_id is not None:
        clauses.append(
            AnalyticsDailyAggregate.product_id.in_(
                select(cast(AnalyticsDimension.natural_key, Uuid)).where(
                    AnalyticsDimension.tenant_id == auth.tenant_id,
                    AnalyticsDimension.dimension_type == "product",
                    AnalyticsDimension.current.is_(True),
                    AnalyticsDimension.attributes["brand_id"].astext == str(filters.brand_id),
                )
            )
        )
    return clauses


def _organizational_filters(auth: AuthContext, filters: AnalyticsFilters) -> list[Any]:
    clauses: list[Any] = [
        analytics_visibility_filter(
            auth,
            "analytics.view",
            AnalyticsDailyAggregate.tenant_id,
            AnalyticsDailyAggregate.company_id,
            AnalyticsDailyAggregate.branch_id,
        ),
        AnalyticsDailyAggregate.date_value >= filters.from_date,
        AnalyticsDailyAggregate.date_value <= filters.to_date,
    ]
    for column, value in (
        (AnalyticsDailyAggregate.company_id, filters.company_id),
        (AnalyticsDailyAggregate.branch_id, filters.branch_id),
    ):
        if value is not None:
            clauses.append(column == value)
    if filters.economic_group_id is not None:
        clauses.append(
            AnalyticsDailyAggregate.company_id.in_(
                select(cast(AnalyticsDimension.natural_key, Uuid)).where(
                    AnalyticsDimension.tenant_id == auth.tenant_id,
                    AnalyticsDimension.dimension_type == "company",
                    AnalyticsDimension.parent_natural_key == str(filters.economic_group_id),
                    AnalyticsDimension.current.is_(True),
                )
            )
        )
    return clauses


def _grain(filters: AnalyticsFilters) -> str:
    selected = [
        ("product", filters.product_id or filters.brand_id),
        ("category", filters.category_id),
        ("supplier", filters.supplier_id),
        ("channel", filters.channel),
    ]
    matches = [grain for grain, value in selected if value is not None]
    if len(matches) > 1:
        raise AppError(
            code="unsupported_filter_combination",
            message="Combine organizational filters with at most one high-cardinality dimension",
            status_code=422,
        )
    return matches[0] if matches else "scope"


async def _dimension_derived_measures(
    session: AsyncSession,
    auth: AuthContext,
    filters: AnalyticsFilters,
    active_days: Decimal,
) -> dict[str, Decimal]:
    """Derive exact cardinality and distribution measures from bounded daily aggregates."""

    derived: dict[str, Decimal] = {}
    if filters.supplier_id is None and filters.channel is None:
        product_clauses = [
            *_organizational_filters(auth, filters),
            AnalyticsDailyAggregate.grain == "product",
        ]
        if filters.product_id is not None:
            product_clauses.append(AnalyticsDailyAggregate.product_id == filters.product_id)
        if filters.category_id is not None:
            product_clauses.append(AnalyticsDailyAggregate.category_id == filters.category_id)
        if filters.brand_id is not None:
            product_clauses.append(
                AnalyticsDailyAggregate.product_id.in_(
                    select(cast(AnalyticsDimension.natural_key, Uuid)).where(
                        AnalyticsDimension.tenant_id == auth.tenant_id,
                        AnalyticsDimension.dimension_type == "product",
                        AnalyticsDimension.current.is_(True),
                        AnalyticsDimension.attributes["brand_id"].astext == str(filters.brand_id),
                    )
                )
            )
        product_rows = list(
            (
                await session.execute(
                    select(
                        AnalyticsDailyAggregate.company_id,
                        AnalyticsDailyAggregate.branch_id,
                        AnalyticsDailyAggregate.product_id,
                        AnalyticsDailyAggregate.date_value,
                        AnalyticsDailyAggregate.measures,
                    )
                    .where(*product_clauses)
                    .limit(_MAX_AGGREGATE_ROWS + 1)
                )
            ).all()
        )
        if len(product_rows) > _MAX_AGGREGATE_ROWS:
            raise AppError(
                code="analytics_cardinality_limit",
                message="Product derivation exceeds the analytical cardinality limit",
                status_code=422,
            )
        sold: dict[UUID, Decimal] = {}
        revenue: dict[UUID, Decimal] = {}
        latest_stock: dict[tuple[UUID | None, UUID | None, UUID], tuple[date, dict[str, Any]]] = {}
        daily_units: list[Decimal] = []
        for company_id, branch_id, product_id, date_value, payload in product_rows:
            if product_id is None:
                continue
            units = _decimal(payload.get("units_sold"))
            sold[product_id] = sold.get(product_id, Decimal(0)) + units
            revenue[product_id] = revenue.get(product_id, Decimal(0)) + _decimal(
                payload.get("product_net_revenue")
            )
            daily_units.append(units)
            stock_key = (company_id, branch_id, product_id)
            previous = latest_stock.get(stock_key)
            if previous is None or date_value > previous[0]:
                latest_stock[stock_key] = (date_value, payload)
        derived["sold_product_count"] = Decimal(sum(value > 0 for value in sold.values()))
        derived["top10_revenue"] = sum(sorted(revenue.values(), reverse=True)[:10], Decimal(0))
        if daily_units:
            mean = sum(daily_units, Decimal(0)) / Decimal(len(daily_units))
            variance = sum((value - mean) ** 2 for value in daily_units) / Decimal(len(daily_units))
            derived["demand_stddev"] = variance.sqrt()
        low_cover = excess = slow = no_sale = 0
        for (_, _, product_id), (_, payload) in latest_stock.items():
            available = _decimal(payload.get("inventory_available"))
            average_units = sold.get(product_id, Decimal(0)) / active_days
            if average_units == 0:
                no_sale += int(available > 0)
                excess += int(available > 0)
                continue
            coverage = available / average_units
            low_cover += int(coverage < 7)
            excess += int(coverage > 90)
            slow += int(coverage > 60)
        derived.update(
            {
                "low_cover_products": Decimal(low_cover),
                "excess_stock_products": Decimal(excess),
                "slow_moving_products": Decimal(slow),
                "no_sale_products": Decimal(no_sale),
            }
        )

    if filters.product_id is None and filters.category_id is None and filters.channel is None:
        supplier_clauses = [
            *_organizational_filters(auth, filters),
            AnalyticsDailyAggregate.grain == "supplier",
        ]
        if filters.supplier_id is not None:
            supplier_clauses.append(AnalyticsDailyAggregate.supplier_id == filters.supplier_id)
        supplier_rows = list(
            (
                await session.execute(
                    select(
                        AnalyticsDailyAggregate.supplier_id,
                        AnalyticsDailyAggregate.measures,
                    )
                    .where(*supplier_clauses)
                    .limit(_MAX_AGGREGATE_ROWS + 1)
                )
            ).all()
        )
        if len(supplier_rows) > _MAX_AGGREGATE_ROWS:
            raise AppError(
                code="analytics_cardinality_limit",
                message="Supplier derivation exceeds the analytical cardinality limit",
                status_code=422,
            )
        supplier_values: dict[UUID, Decimal] = {}
        supplier_products: dict[UUID, Decimal] = {}
        for supplier_id, payload in supplier_rows:
            if supplier_id is None:
                continue
            supplier_values[supplier_id] = supplier_values.get(supplier_id, Decimal(0)) + _decimal(
                payload.get("purchase_value")
            )
            supplier_products[supplier_id] = supplier_products.get(
                supplier_id, Decimal(0)
            ) + _decimal(payload.get("supplier_product_count"))
        active_suppliers = [supplier for supplier, amount in supplier_values.items() if amount > 0]
        ordered_values = sorted(supplier_values.values(), reverse=True)
        derived["active_supplier_count"] = Decimal(len(active_suppliers))
        derived["top_supplier_value"] = ordered_values[0] if ordered_values else Decimal(0)
        derived["top5_supplier_value"] = sum(ordered_values[:5], Decimal(0))
        # Supplier-product coverage is based on the conformed supplier grain. The
        # value is additive across suppliers and remains tenant/scope filtered.
        derived["supplier_product_count"] = sum(supplier_products.values(), Decimal(0))
    return derived


async def _measure_snapshot(
    session: AsyncSession, auth: AuthContext, filters: AnalyticsFilters
) -> tuple[dict[str, Decimal], datetime | None, bool]:
    rows = list(
        (
            await session.execute(
                select(
                    AnalyticsDailyAggregate.measures,
                    AnalyticsDailyAggregate.date_value,
                    AnalyticsDailyAggregate.source_max_updated_at,
                    AnalyticsDailyAggregate.company_id,
                    AnalyticsDailyAggregate.branch_id,
                    AnalyticsDailyAggregate.product_id,
                    AnalyticsDailyAggregate.category_id,
                    AnalyticsDailyAggregate.supplier_id,
                )
                .where(
                    *_aggregate_filters(auth, filters),
                    AnalyticsDailyAggregate.grain == _grain(filters),
                )
                .limit(_MAX_AGGREGATE_ROWS + 1)
            )
        ).all()
    )
    if len(rows) > _MAX_AGGREGATE_ROWS:
        raise AppError(
            code="analytics_cardinality_limit",
            message="The query exceeds the analytical cardinality limit",
            status_code=422,
        )
    measures: dict[str, Decimal] = {}
    point_by_entity: dict[
        tuple[UUID | None, UUID | None, UUID | None, UUID | None, UUID | None],
        tuple[date, dict[str, Decimal]],
    ] = {}
    point_period_total: dict[str, Decimal] = {}
    dates: set[date] = set()
    freshness: datetime | None = None
    for (
        payload,
        date_value,
        source_updated_at,
        company_id,
        branch_id,
        product_id,
        category_id,
        supplier_id,
    ) in rows:
        dates.add(date_value)
        freshness = max(freshness, source_updated_at) if freshness else source_updated_at
        entity = (company_id, branch_id, product_id, category_id, supplier_id)
        point_values = {
            key: _decimal(value) for key, value in payload.items() if key in _POINT_IN_TIME_MEASURES
        }
        current_point = point_by_entity.get(entity)
        if current_point is None or date_value >= current_point[0]:
            point_by_entity[entity] = (date_value, point_values)
        for key, value in payload.items():
            decimal_value = _decimal(value)
            if key in _POINT_IN_TIME_MEASURES:
                point_period_total[key] = point_period_total.get(key, Decimal(0)) + decimal_value
            else:
                measures[key] = measures.get(key, Decimal(0)) + decimal_value
    for _, point_values in point_by_entity.values():
        for key, value in point_values.items():
            measures[key] = measures.get(key, Decimal(0)) + value
    if _grain(filters) in {"product", "category"}:
        measures["gross_revenue"] = measures.get("product_gross_revenue", Decimal(0))
        measures["net_revenue"] = measures.get("product_net_revenue", Decimal(0))
        measures["discount_amount"] = measures.get("product_discount_amount", Decimal(0))
        measures["sales_tax"] = measures.get("product_sales_tax", Decimal(0))
        measures["scoped_net_revenue"] = measures.get("product_net_revenue", Decimal(0))
        measures["scoped_gross_profit"] = measures.get("product_gross_profit", Decimal(0))
        measures["purchase_value"] = measures.get("product_purchase_value", Decimal(0))
    active_days = Decimal(max(len(dates), 1))
    measures["active_days"] = active_days
    measures["active_hours"] = active_days * Decimal(24)
    measures["average_daily_units"] = measures.get("units_sold", Decimal(0)) / active_days
    measures["average_inventory_cost"] = (
        point_period_total.get("inventory_cost_value", Decimal(0)) / active_days
    )
    price_count = measures.get("price_count", Decimal(0))
    if price_count:
        average_price = measures.get("price_value", Decimal(0)) / price_count
        variance = max(
            measures.get("price_value_squared", Decimal(0)) / price_count
            - average_price * average_price,
            Decimal(0),
        )
        measures["average_price"] = average_price
        measures["price_stddev"] = variance.sqrt()
    measures["gross_profit"] = measures.get(
        "gross_profit", measures.get("net_revenue", Decimal(0)) - measures.get("cogs", Decimal(0))
    )
    measures["network_net_revenue"] = measures.get("net_revenue", Decimal(0))
    measures["scoped_net_revenue"] = measures.get(
        "scoped_net_revenue", measures.get("net_revenue", Decimal(0))
    )
    measures["scoped_gross_profit"] = measures.get(
        "scoped_gross_profit", measures.get("gross_profit", Decimal(0))
    )
    measures["units_available_for_sale"] = measures.get(
        "inventory_available", Decimal(0)
    ) + measures.get("units_sold", Decimal(0))
    measures["freshness_seconds"] = (
        Decimal(max(int((datetime.now(UTC) - freshness).total_seconds()), 0))
        if freshness
        else Decimal(0)
    )
    measures.update(await _dimension_derived_measures(session, auth, filters, active_days))
    return measures, freshness, bool(rows)


async def _goal_value(
    session: AsyncSession, auth: AuthContext, filters: AnalyticsFilters, code: str
) -> Decimal | None:
    if auth.tenant_id is None:
        return None
    goal = await session.scalar(
        select(AnalyticsGoal)
        .where(
            AnalyticsGoal.tenant_id == auth.tenant_id,
            AnalyticsGoal.kpi_code == code,
            AnalyticsGoal.active.is_(True),
            AnalyticsGoal.period_start <= filters.to_date,
            AnalyticsGoal.period_end >= filters.from_date,
            or_(AnalyticsGoal.company_id == filters.company_id, AnalyticsGoal.company_id.is_(None)),
            or_(AnalyticsGoal.branch_id == filters.branch_id, AnalyticsGoal.branch_id.is_(None)),
        )
        .order_by(AnalyticsGoal.branch_id.desc(), AnalyticsGoal.company_id.desc())
    )
    return goal.target_value if goal else None


def _variation(
    current: Decimal | None, comparison: Decimal | None
) -> tuple[Decimal | None, Decimal | None]:
    if current is None or comparison is None:
        return None, None
    absolute = (current - comparison).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    percentage = (
        None
        if comparison == 0
        else (absolute / comparison * 100).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    )
    return absolute, percentage


def _target_status(
    definition: KpiDefinition, value: Decimal | None, target: Decimal | None
) -> str | None:
    if value is None or target is None:
        return None
    if definition.desirable_direction == "decrease":
        return "met" if value <= target else "below"
    return "met" if value >= target else "below"


async def calculate_kpi(
    session: AsyncSession,
    redis: Redis,
    auth: AuthContext,
    filters: AnalyticsFilters,
    code: str,
) -> tuple[KpiResultResponse, str]:
    definition = KPI_BY_CODE.get(code)
    if definition is None:
        raise AppError(code="kpi_not_found", message="KPI not found", status_code=404)
    _validate_access(auth, definition, filters)
    if auth.tenant_id is None:
        raise AppError(code="tenant_context_required", message="Select a tenant", status_code=409)
    data_version = await session.scalar(
        select(AnalyticsDataVersion).where(AnalyticsDataVersion.tenant_id == auth.tenant_id)
    )
    version = data_version.current_version if data_version else 0
    identity = _cache_identity(auth.tenant_id, auth, filters, definition, version)
    cache_key = f"analytics:kpi:{identity}"
    metric_key = cache_metric_key(auth)
    cache_bypass = code == "operations.cache_hit_rate"
    try:
        cached = None if cache_bypass else await redis.get(cache_key)
        await redis.hincrby(metric_key, "requests", 1)
        if cached:
            await redis.hincrby(metric_key, "hits", 1)
        await redis.expire(metric_key, 86_400 * 30)
    except RedisError as exc:
        raise AppError(
            code="analytics_cache_unavailable",
            message="Analytical cache is temporarily unavailable",
            status_code=503,
        ) from exc
    if cached:
        response = KpiResultResponse.model_validate_json(cached)
        # Goals are governance state and do not advance the warehouse data
        # version. Overlay the current authorized target on every cache hit so
        # a newly-created or edited goal is visible immediately.
        target = await _goal_value(session, auth, filters, code)
        return (
            response.model_copy(
                update={
                    "cache_status": "hit",
                    "target_value": target,
                    "target_status": _target_status(definition, response.value, target),
                }
            ),
            identity,
        )
    measures, freshness, has_data = await _measure_snapshot(session, auth, filters)
    if cache_bypass:
        try:
            cache_metrics = await redis.hgetall(metric_key)
        except RedisError as exc:
            raise AppError(
                code="analytics_cache_unavailable",
                message="Analytical cache is temporarily unavailable",
                status_code=503,
            ) from exc
        measures["cache_requests"] = _decimal(
            cache_metrics.get(b"requests", cache_metrics.get("requests", 0))
        )
        measures["cache_hits"] = _decimal(cache_metrics.get(b"hits", cache_metrics.get("hits", 0)))
    value_result = evaluate_formula(definition.formula, measures) if has_data else None
    period_days = (filters.to_date - filters.from_date).days + 1
    previous_filters = filters.model_copy(
        update={
            "from_date": filters.from_date - timedelta(days=period_days),
            "to_date": filters.from_date - timedelta(days=1),
        }
    )
    previous_measures, _, previous_has_data = await _measure_snapshot(
        session, auth, previous_filters
    )
    previous = (
        None
        if cache_bypass
        else evaluate_formula(definition.formula, previous_measures)
        if previous_has_data
        else None
    )
    absolute, percentage = _variation(value_result, previous)
    target = await _goal_value(session, auth, filters, code)
    response = KpiResultResponse(
        code=code,
        name=definition.name,
        category=definition.category,
        unit=definition.unit,
        value=value_result,
        reason=None
        if has_data and value_result is not None
        else "zero_denominator"
        if has_data
        else "no_data",
        formula_version=definition.version,
        period_start=filters.from_date,
        period_end=filters.to_date,
        comparison_value=previous,
        absolute_variation=absolute,
        percentage_variation=percentage,
        target_value=target,
        target_status=_target_status(definition, value_result, target),
        freshness_at=freshness or (data_version.freshness_at if data_version else None),
        quality_score=data_version.quality_score if data_version else None,
        data_version=version,
        cache_status="bypass" if cache_bypass else "miss",
    )
    if not cache_bypass:
        try:
            await redis.setex(cache_key, _CACHE_TTL_SECONDS, response.model_dump_json())
        except RedisError as exc:
            raise AppError(
                code="analytics_cache_unavailable",
                message="Analytical cache is temporarily unavailable",
                status_code=503,
            ) from exc
    scope_hash = _cache_identity(auth.tenant_id, auth, filters, definition, 0)
    existing = await session.scalar(
        select(AnalyticsKpiResult).where(
            AnalyticsKpiResult.tenant_id == auth.tenant_id,
            AnalyticsKpiResult.kpi_code == code,
            AnalyticsKpiResult.formula_version == definition.version,
            AnalyticsKpiResult.scope_hash == scope_hash,
            AnalyticsKpiResult.period_start == filters.from_date,
            AnalyticsKpiResult.period_end == filters.to_date,
            AnalyticsKpiResult.data_version == version,
        )
    )
    if existing is None and freshness is not None:
        session.add(
            AnalyticsKpiResult(
                tenant_id=auth.tenant_id,
                kpi_code=code,
                formula_version=definition.version,
                scope_hash=scope_hash,
                filters=filters.model_dump(mode="json"),
                period_start=filters.from_date,
                period_end=filters.to_date,
                value=value_result,
                reason=response.reason,
                comparison=response.model_dump(
                    mode="json",
                    include={
                        "comparison_value",
                        "absolute_variation",
                        "percentage_variation",
                        "target_value",
                        "target_status",
                    },
                ),
                freshness_at=freshness,
                calculated_at=datetime.now(UTC),
                data_version=version,
            )
        )
    return response, identity


def _previous_year(value: date) -> date:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)


async def _calculated_value(
    session: AsyncSession,
    auth: AuthContext,
    filters: AnalyticsFilters,
    definition: KpiDefinition,
) -> Decimal | None:
    measures, _, has_data = await _measure_snapshot(session, auth, filters)
    return evaluate_formula(definition.formula, measures) if has_data else None


async def calculate_comparisons(
    session: AsyncSession,
    redis: Redis,
    auth: AuthContext,
    filters: AnalyticsFilters,
    code: str,
) -> KpiComparisonResponse:
    definition = KPI_BY_CODE.get(code)
    if definition is None:
        raise AppError(code="kpi_not_found", message="KPI not found", status_code=404)
    current, _ = await calculate_kpi(session, redis, auth, filters, code)
    year_filters = filters.model_copy(
        update={
            "from_date": _previous_year(filters.from_date),
            "to_date": _previous_year(filters.to_date),
        }
    )
    year_value = await _calculated_value(session, auth, year_filters, definition)
    trailing_filters = filters.model_copy(
        update={"from_date": filters.to_date - timedelta(days=27)}
    )
    trailing_points = await time_series(session, auth, trailing_filters, code)
    trailing_values = [point.value for point in trailing_points if point.value is not None]
    moving_average = (
        sum(trailing_values, Decimal(0)) / Decimal(len(trailing_values))
        if trailing_values
        else None
    )
    network_value: Decimal | None = None
    if (
        auth.tenant_id is not None
        and (filters.company_id is not None or filters.branch_id is not None)
        and auth.has_tenant_wide_permission("analytics.view", auth.tenant_id)
    ):
        network_filters = filters.model_copy(update={"company_id": None, "branch_id": None})
        network_value = await _calculated_value(session, auth, network_filters, definition)
    category_value: Decimal | None = None
    if filters.product_id is not None and auth.tenant_id is not None:
        parent = await session.scalar(
            select(AnalyticsDimension.parent_natural_key).where(
                AnalyticsDimension.tenant_id == auth.tenant_id,
                AnalyticsDimension.dimension_type == "product",
                AnalyticsDimension.natural_key == str(filters.product_id),
                AnalyticsDimension.current.is_(True),
            )
        )
        if parent:
            category_filters = filters.model_copy(
                update={"product_id": None, "category_id": UUID(parent), "brand_id": None}
            )
            category_value = await _calculated_value(session, auth, category_filters, definition)
    return KpiComparisonResponse.model_validate(
        {
            **current.model_dump(),
            "same_period_last_year_value": year_value,
            "moving_average_28d_value": moving_average,
            "authorized_network_value": network_value,
            "category_value": category_value,
        }
    )


async def time_series(
    session: AsyncSession, auth: AuthContext, filters: AnalyticsFilters, code: str
) -> list[TimeSeriesPoint]:
    definition = KPI_BY_CODE.get(code)
    if definition is None:
        raise AppError(code="kpi_not_found", message="KPI not found", status_code=404)
    _validate_access(auth, definition, filters)
    rows = list(
        (
            await session.execute(
                select(AnalyticsDailyAggregate.date_value, AnalyticsDailyAggregate.measures)
                .where(
                    *_aggregate_filters(auth, filters),
                    AnalyticsDailyAggregate.grain == _grain(filters),
                )
                .order_by(AnalyticsDailyAggregate.date_value)
                .limit(_MAX_AGGREGATE_ROWS)
            )
        ).all()
    )
    by_date: dict[date, dict[str, Decimal]] = {}
    for date_value, payload in rows:
        target = by_date.setdefault(date_value, {})
        for key, value in payload.items():
            target[key] = target.get(key, Decimal(0)) + _decimal(value)
    points: list[TimeSeriesPoint] = []
    for date_value, measures in sorted(by_date.items()):
        if _grain(filters) in {"product", "category"}:
            measures["gross_revenue"] = measures.get("product_gross_revenue", Decimal(0))
            measures["net_revenue"] = measures.get("product_net_revenue", Decimal(0))
            measures["discount_amount"] = measures.get("product_discount_amount", Decimal(0))
            measures["scoped_net_revenue"] = measures.get("product_net_revenue", Decimal(0))
            measures["scoped_gross_profit"] = measures.get("product_gross_profit", Decimal(0))
        measures["active_days"] = Decimal(1)
        measures["active_hours"] = Decimal(24)
        measures["average_daily_units"] = measures.get("units_sold", Decimal(0))
        measures["average_inventory_cost"] = measures.get("inventory_cost_value", Decimal(0))
        measures["gross_profit"] = measures.get(
            "gross_profit",
            measures.get("net_revenue", Decimal(0)) - measures.get("cogs", Decimal(0)),
        )
        points.append(
            TimeSeriesPoint(period=date_value, value=evaluate_formula(definition.formula, measures))
        )
    return points


async def ranking(
    session: AsyncSession,
    auth: AuthContext,
    filters: AnalyticsFilters,
    code: str,
    dimension: str,
    limit: int,
) -> list[RankingItem]:
    definition = KPI_BY_CODE.get(code)
    if definition is None:
        raise AppError(code="kpi_not_found", message="KPI not found", status_code=404)
    if dimension not in {"product", "category", "supplier", "channel"}:
        raise AppError(
            code="invalid_dimension", message="Unsupported ranking dimension", status_code=422
        )
    _validate_access(auth, definition, filters)
    rows = list(
        (
            await session.execute(
                select(AnalyticsDailyAggregate).where(
                    *_aggregate_filters(auth, filters),
                    AnalyticsDailyAggregate.grain == dimension,
                )
            )
        ).scalars()
    )
    grouped: dict[str, dict[str, Decimal]] = {}
    for row in rows:
        key = str(
            row.product_id
            if dimension == "product"
            else row.category_id
            if dimension == "category"
            else row.supplier_id
            if dimension == "supplier"
            else row.dimension_value
        )
        target = grouped.setdefault(key, {})
        for measure, value in row.measures.items():
            target[measure] = target.get(measure, Decimal(0)) + _decimal(value)
    if dimension in {"product", "category"}:
        for measures in grouped.values():
            measures["gross_revenue"] = measures.get("product_gross_revenue", Decimal(0))
            measures["net_revenue"] = measures.get("product_net_revenue", Decimal(0))
            measures["discount_amount"] = measures.get("product_discount_amount", Decimal(0))
            measures["scoped_net_revenue"] = measures.get("product_net_revenue", Decimal(0))
            measures["scoped_gross_profit"] = measures.get("product_gross_profit", Decimal(0))
            measures["purchase_value"] = measures.get("product_purchase_value", Decimal(0))
    evaluated = [
        (key, evaluate_formula(definition.formula, measures)) for key, measures in grouped.items()
    ]
    evaluated.sort(key=lambda item: item[1] or Decimal(0), reverse=True)
    total = sum((value or Decimal(0) for _, value in evaluated), Decimal(0))
    labels: dict[str, str] = {}
    if auth.tenant_id is not None and evaluated:
        labels = {
            item.natural_key: item.label
            for item in (
                await session.scalars(
                    select(AnalyticsDimension).where(
                        AnalyticsDimension.tenant_id == auth.tenant_id,
                        AnalyticsDimension.dimension_type == dimension,
                        AnalyticsDimension.natural_key.in_([key for key, _ in evaluated[:limit]]),
                        AnalyticsDimension.current.is_(True),
                    )
                )
            ).all()
        }
    return [
        RankingItem(
            dimension_key=key,
            label=labels.get(key, key),
            value=value_result,
            share_percent=None
            if total == 0 or value_result is None
            else (value_result / total * 100).quantize(Decimal("0.0001")),
            rank=index,
        )
        for index, (key, value_result) in enumerate(evaluated[:limit], start=1)
    ]


async def composition(
    session: AsyncSession,
    auth: AuthContext,
    filters: AnalyticsFilters,
    code: str,
    dimension: str,
    limit: int,
) -> list[CompositionItem]:
    ranked = await ranking(session, auth, filters, code, dimension, limit)
    return [
        CompositionItem(
            dimension_key=item.dimension_key,
            label=item.label,
            value=item.value,
            percent=item.share_percent,
        )
        for item in ranked
    ]


async def drill_down(
    session: AsyncSession,
    auth: AuthContext,
    filters: AnalyticsFilters,
    code: str,
    limit: int,
    offset: int,
) -> list[DrillDownItem]:
    definition = KPI_BY_CODE.get(code)
    if definition is None:
        raise AppError(code="kpi_not_found", message="KPI not found", status_code=404)
    _validate_access(auth, definition, filters)
    if not auth.has_permission("analytics.detail"):
        raise AppError(
            code="analytics_detail_forbidden", message="Detail permission required", status_code=403
        )
    clauses: list[Any] = [
        analytics_visibility_filter(
            auth,
            "analytics.detail",
            AnalyticsFact.tenant_id,
            AnalyticsFact.company_id,
            AnalyticsFact.branch_id,
        ),
        AnalyticsFact.date_value >= filters.from_date,
        AnalyticsFact.date_value <= filters.to_date,
        or_(*(AnalyticsFact.measures.has_key(key) for key in definition.required_fields)),
    ]
    for column, value in (
        (AnalyticsFact.company_id, filters.company_id),
        (AnalyticsFact.branch_id, filters.branch_id),
        (AnalyticsFact.product_id, filters.product_id),
        (AnalyticsFact.category_id, filters.category_id),
        (AnalyticsFact.supplier_id, filters.supplier_id),
        (AnalyticsFact.channel, filters.channel),
    ):
        if value is not None:
            clauses.append(column == value)
    if filters.economic_group_id is not None:
        clauses.append(
            AnalyticsFact.company_id.in_(
                select(cast(AnalyticsDimension.natural_key, Uuid)).where(
                    AnalyticsDimension.tenant_id == auth.tenant_id,
                    AnalyticsDimension.dimension_type == "company",
                    AnalyticsDimension.parent_natural_key == str(filters.economic_group_id),
                    AnalyticsDimension.current.is_(True),
                )
            )
        )
    if filters.brand_id is not None:
        clauses.append(
            AnalyticsFact.product_id.in_(
                select(cast(AnalyticsDimension.natural_key, Uuid)).where(
                    AnalyticsDimension.tenant_id == auth.tenant_id,
                    AnalyticsDimension.dimension_type == "product",
                    AnalyticsDimension.current.is_(True),
                    AnalyticsDimension.attributes["brand_id"].astext == str(filters.brand_id),
                )
            )
        )
    rows = (
        await session.execute(
            select(AnalyticsFact, AnalyticsLineage)
            .outerjoin(
                AnalyticsLineage,
                and_(
                    AnalyticsLineage.tenant_id == AnalyticsFact.tenant_id,
                    AnalyticsLineage.fact_id == AnalyticsFact.id,
                ),
            )
            .where(*clauses)
            .order_by(AnalyticsFact.occurred_at.desc(), AnalyticsFact.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [
        DrillDownItem(
            fact_id=fact.id,
            fact_type=fact.fact_type,
            occurred_at=fact.occurred_at,
            company_id=fact.company_id,
            branch_id=fact.branch_id,
            product_id=fact.product_id,
            supplier_id=fact.supplier_id,
            canonical_table=fact.canonical_table,
            canonical_record_id=fact.canonical_record_id,
            canonical_version=fact.canonical_version,
            measures=fact.measures,
            source_batch_id=lineage.source_batch_id if lineage else fact.batch_id,
            transformation_version=lineage.transformation_version if lineage else None,
        )
        for fact, lineage in rows
    ]


def catalog(category: str | None = None) -> list[KpiDefinition]:
    return [item for item in KPI_CATALOG if category is None or item.category == category]
