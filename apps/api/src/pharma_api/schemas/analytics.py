from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnalyticsFilters(BaseModel):
    from_date: date
    to_date: date
    economic_group_id: UUID | None = None
    company_id: UUID | None = None
    branch_id: UUID | None = None
    product_id: UUID | None = None
    category_id: UUID | None = None
    brand_id: UUID | None = None
    supplier_id: UUID | None = None
    channel: str | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def validate_period(self) -> AnalyticsFilters:
        if self.to_date < self.from_date:
            raise ValueError("to_date must not precede from_date")
        if (self.to_date - self.from_date).days > 731:
            raise ValueError("analytics queries are limited to 732 days")
        if self.branch_id is not None and self.company_id is None:
            raise ValueError("branch_id requires company_id")
        return self


class FormulaResponse(BaseModel):
    operation: str
    operands: list[str]
    scale: str


class KpiCatalogResponse(BaseModel):
    code: str
    name: str
    description: str
    category: str
    objective: str
    formula: FormulaResponse
    unit: str
    desirable_direction: str
    grain: str
    dimensions: list[str]
    filters: list[str]
    required_fields: list[str]
    data_source: str
    periodicity: str
    version: int
    owner: str
    status: str
    null_rule: str
    zero_division_rule: str
    rounding_rule: str
    comparison_rule: str
    dependencies: list[str]
    limitations: list[str]
    interpretation: str
    impact: str
    drill_down: str
    last_updated_at: datetime | None = None


class UnavailableKpiResponse(BaseModel):
    code: str
    name: str
    category: str
    required_data: list[str]
    reason: str
    status: Literal["unavailable"]


class KpiResultResponse(BaseModel):
    code: str
    name: str
    category: str
    unit: str
    value: Decimal | None
    reason: str | None
    formula_version: int
    period_start: date
    period_end: date
    comparison_value: Decimal | None = None
    absolute_variation: Decimal | None = None
    percentage_variation: Decimal | None = None
    target_value: Decimal | None = None
    target_status: str | None = None
    freshness_at: datetime | None
    quality_score: Decimal | None
    data_version: int
    cache_status: Literal["hit", "miss", "bypass"]


class KpiComparisonResponse(KpiResultResponse):
    same_period_last_year_value: Decimal | None = None
    moving_average_28d_value: Decimal | None = None
    authorized_network_value: Decimal | None = None
    category_value: Decimal | None = None


class TimeSeriesPoint(BaseModel):
    period: date
    value: Decimal | None
    comparison_value: Decimal | None = None
    target_value: Decimal | None = None


class RankingItem(BaseModel):
    dimension_key: str
    label: str
    value: Decimal | None
    share_percent: Decimal | None
    rank: int


class CompositionItem(BaseModel):
    dimension_key: str
    label: str
    value: Decimal | None
    percent: Decimal | None


class DrillDownItem(BaseModel):
    fact_id: UUID
    fact_type: str
    occurred_at: datetime
    company_id: UUID | None
    branch_id: UUID | None
    product_id: UUID | None
    supplier_id: UUID | None
    canonical_table: str
    canonical_record_id: str
    canonical_version: str
    measures: dict[str, Any]
    source_batch_id: UUID | None
    transformation_version: str | None


class AvailableFiltersResponse(BaseModel):
    economic_groups: list[dict[str, str]]
    companies: list[dict[str, str]]
    branches: list[dict[str, str]]
    products: list[dict[str, str]]
    categories: list[dict[str, str]]
    brands: list[dict[str, str]]
    suppliers: list[dict[str, str]]
    channels: list[str]
    minimum_date: date | None
    maximum_date: date | None


class FreshnessResponse(BaseModel):
    data_version: int
    watermark: datetime | None
    freshness_at: datetime | None
    lag_seconds: int | None
    quality_score: Decimal | None
    last_refresh_job_id: UUID | None


class AnalyticsGoalCreateRequest(BaseModel):
    company_id: UUID | None = None
    branch_id: UUID | None = None
    kpi_code: str = Field(min_length=3, max_length=140)
    period_start: date
    period_end: date
    target_value: Decimal | None = None
    lower_value: Decimal | None = None
    upper_value: Decimal | None = None
    direction: Literal["increase", "decrease", "target"]
    owner_user_id: UUID
    note: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_goal(self) -> AnalyticsGoalCreateRequest:
        if self.period_end < self.period_start:
            raise ValueError("period_end must not precede period_start")
        if self.branch_id is not None and self.company_id is None:
            raise ValueError("branch_id requires company_id")
        if self.target_value is None and self.lower_value is None and self.upper_value is None:
            raise ValueError("a target value or interval is required")
        if (
            self.lower_value is not None
            and self.upper_value is not None
            and self.upper_value < self.lower_value
        ):
            raise ValueError("upper_value must not be lower than lower_value")
        return self


class AnalyticsGoalUpdateRequest(BaseModel):
    target_value: Decimal | None = None
    lower_value: Decimal | None = None
    upper_value: Decimal | None = None
    direction: Literal["increase", "decrease", "target"] | None = None
    owner_user_id: UUID | None = None
    note: str | None = Field(default=None, max_length=2_000)
    active: bool | None = None
    expected_version: int = Field(ge=1)
    change_reason: str = Field(min_length=3, max_length=500)


class AnalyticsGoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    company_id: UUID | None
    branch_id: UUID | None
    kpi_code: str
    period_start: date
    period_end: date
    target_value: Decimal | None
    lower_value: Decimal | None
    upper_value: Decimal | None
    direction: str
    owner_user_id: UUID
    note: str | None
    active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class RefreshRequest(BaseModel):
    from_date: date
    to_date: date
    idempotency_key: str = Field(min_length=8, max_length=180)
    mode: Literal["recompute", "backfill"] = "recompute"

    @model_validator(mode="after")
    def validate_window(self) -> RefreshRequest:
        if self.to_date < self.from_date:
            raise ValueError("to_date must not precede from_date")
        if (self.to_date - self.from_date).days > 3_650:
            raise ValueError("backfill windows are limited to ten years per request")
        return self


class RefreshJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    trigger_type: str
    source_batch_id: UUID | None
    state: str
    window_start: datetime
    window_end: datetime
    watermark_before: datetime | None
    watermark_after: datetime | None
    checkpoint: dict[str, Any]
    metrics: dict[str, Any]
    attempt_count: int
    cancel_requested_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None
    version: int
