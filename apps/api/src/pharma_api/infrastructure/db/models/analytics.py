from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pharma_api.infrastructure.db.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionMixin,
)

DIMENSION_TYPES = (
    "date",
    "hour",
    "tenant",
    "economic_group",
    "company",
    "branch",
    "product",
    "product_identifier",
    "category",
    "category_hierarchy",
    "brand",
    "manufacturer",
    "supplier",
    "channel",
    "payment_method",
    "sale_origin",
    "movement_type",
    "promotion",
    "price_band",
    "commercial_classification",
)

FACT_TYPES = (
    "sale",
    "sale_item",
    "payment",
    "return",
    "purchase",
    "purchase_item",
    "receipt",
    "inventory_movement",
    "stock_snapshot",
    "price",
    "promotion",
    "cost",
    "data_quality",
    "import_execution",
)


class AnalyticsDimension(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    """SCD2 dimension envelope for typed analytical members."""

    __tablename__ = "analytics_dimensions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "dimension_type",
            "natural_key",
            "effective_from",
            name="uq_analytics_dimensions_version",
        ),
        CheckConstraint(
            f"dimension_type IN ({','.join(repr(item) for item in DIMENSION_TYPES)})",
            name="ck_analytics_dimensions_type",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_analytics_dimensions_period",
        ),
        Index(
            "uq_analytics_dimensions_current",
            "tenant_id",
            "dimension_type",
            "natural_key",
            unique=True,
            postgresql_where=text("current = true"),
        ),
        Index("ix_analytics_dimensions_lookup", "tenant_id", "dimension_type", "natural_key"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    dimension_type: Mapped[str] = mapped_column(String(40), nullable=False)
    natural_key: Mapped[str] = mapped_column(String(300), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String(300))
    parent_natural_key: Mapped[str | None] = mapped_column(String(300))
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class AnalyticsFact(UUIDPrimaryKeyMixin, Base):
    """Conformed fact envelope. `fact_type` defines the documented grain and measure set."""

    __tablename__ = "analytics_facts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_analytics_facts_tenant_id"),
        UniqueConstraint("tenant_id", "fact_type", "grain_key", name="uq_analytics_facts_grain"),
        CheckConstraint(
            f"fact_type IN ({','.join(repr(item) for item in FACT_TYPES)})",
            name="ck_analytics_facts_type",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_analytics_facts_company_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_analytics_facts_branch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            ondelete="RESTRICT",
            name="fk_analytics_facts_product_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["canonical_categories.tenant_id", "canonical_categories.id"],
            ondelete="RESTRICT",
            name="fk_analytics_facts_category_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["canonical_suppliers.tenant_id", "canonical_suppliers.id"],
            ondelete="RESTRICT",
            name="fk_analytics_facts_supplier_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "promotion_id"],
            ["canonical_promotions.tenant_id", "canonical_promotions.id"],
            ondelete="RESTRICT",
            name="fk_analytics_facts_promotion_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="RESTRICT",
            name="fk_analytics_facts_batch_same_tenant",
        ),
        Index(
            "ix_analytics_facts_scope_date",
            "tenant_id",
            "company_id",
            "branch_id",
            "date_value",
            "fact_type",
        ),
        Index("ix_analytics_facts_product_date", "tenant_id", "product_id", "date_value"),
        Index("ix_analytics_facts_supplier_date", "tenant_id", "supplier_id", "date_value"),
        Index("ix_analytics_facts_date_brin", "occurred_at", postgresql_using="brin"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    fact_type: Mapped[str] = mapped_column(String(40), nullable=False)
    grain_key: Mapped[str] = mapped_column(String(500), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    date_value: Mapped[date] = mapped_column(Date, nullable=False)
    hour_value: Mapped[int | None] = mapped_column(Integer)
    company_id: Mapped[UUID | None] = mapped_column()
    branch_id: Mapped[UUID | None] = mapped_column()
    product_id: Mapped[UUID | None] = mapped_column()
    category_id: Mapped[UUID | None] = mapped_column()
    supplier_id: Mapped[UUID | None] = mapped_column()
    channel: Mapped[str | None] = mapped_column(String(60))
    payment_method: Mapped[str | None] = mapped_column(String(60))
    movement_type: Mapped[str | None] = mapped_column(String(40))
    promotion_id: Mapped[UUID | None] = mapped_column()
    batch_id: Mapped[UUID | None] = mapped_column()
    canonical_table: Mapped[str] = mapped_column(String(100), nullable=False)
    canonical_record_id: Mapped[str] = mapped_column(String(300), nullable=False)
    canonical_version: Mapped[str] = mapped_column(String(100), nullable=False)
    measures: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    dimension_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_version: Mapped[int] = mapped_column(BigInteger, nullable=False)


class AnalyticsDailyAggregate(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "analytics_daily_aggregates"
    __table_args__ = (
        Index(
            "uq_analytics_daily_aggregate_grain",
            "tenant_id",
            "date_value",
            "grain",
            "company_id",
            "branch_id",
            "product_id",
            "category_id",
            "supplier_id",
            "dimension_value",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        Index(
            "ix_analytics_daily_aggregate_query",
            "tenant_id",
            "grain",
            "date_value",
            "company_id",
            "branch_id",
        ),
        Index("ix_analytics_daily_aggregate_date_brin", "date_value", postgresql_using="brin"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_analytics_aggregate_company_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_analytics_aggregate_branch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            ondelete="RESTRICT",
            name="fk_analytics_aggregate_product_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["canonical_categories.tenant_id", "canonical_categories.id"],
            ondelete="RESTRICT",
            name="fk_analytics_aggregate_category_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["canonical_suppliers.tenant_id", "canonical_suppliers.id"],
            ondelete="RESTRICT",
            name="fk_analytics_aggregate_supplier_same_tenant",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    date_value: Mapped[date] = mapped_column(Date, nullable=False)
    grain: Mapped[str] = mapped_column(String(40), nullable=False)
    company_id: Mapped[UUID | None] = mapped_column()
    branch_id: Mapped[UUID | None] = mapped_column()
    product_id: Mapped[UUID | None] = mapped_column()
    category_id: Mapped[UUID | None] = mapped_column()
    supplier_id: Mapped[UUID | None] = mapped_column()
    dimension_value: Mapped[str | None] = mapped_column(String(300))
    measures: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    source_max_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_version: Mapped[int] = mapped_column(BigInteger, nullable=False)


class AnalyticsKpiDefinitionVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "analytics_kpi_definition_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "kpi_code",
            "formula_version",
            name="uq_analytics_kpi_version",
        ),
        Index("ix_analytics_kpi_catalog", "tenant_id", "category", "status", "kpi_code"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    kpi_code: Mapped[str] = mapped_column(String(140), nullable=False)
    formula_version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AnalyticsKpiResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "analytics_kpi_results"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "kpi_code",
            "formula_version",
            "scope_hash",
            "period_start",
            "period_end",
            "data_version",
            name="uq_analytics_kpi_result_version",
        ),
        Index("ix_analytics_kpi_results_lookup", "tenant_id", "kpi_code", "period_end"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    kpi_code: Mapped[str] = mapped_column(String(140), nullable=False)
    formula_version: Mapped[int] = mapped_column(Integer, nullable=False)
    scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    reason: Mapped[str | None] = mapped_column(String(80))
    comparison: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    freshness_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_version: Mapped[int] = mapped_column(BigInteger, nullable=False)


class AnalyticsRefreshJob(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "analytics_refresh_jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_analytics_refresh_tenant_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_analytics_refresh_idempotency"),
        CheckConstraint(
            "state IN ('queued','running','completed','failed','cancelled')",
            name="ck_analytics_refresh_state",
        ),
        CheckConstraint("window_end >= window_start", name="ck_analytics_refresh_window"),
        Index(
            "uq_analytics_refresh_running",
            "tenant_id",
            unique=True,
            postgresql_where=text("state = 'running'"),
        ),
        Index("ix_analytics_refresh_queue", "state", "created_at"),
        ForeignKeyConstraint(
            ["tenant_id", "source_batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="RESTRICT",
            name="fk_analytics_refresh_batch_same_tenant",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_batch_id: Mapped[UUID | None] = mapped_column()
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    watermark_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    watermark_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)


class AnalyticsDataVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "analytics_data_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_analytics_data_versions_tenant"),
        ForeignKeyConstraint(
            ["tenant_id", "last_refresh_job_id"],
            ["analytics_refresh_jobs.tenant_id", "analytics_refresh_jobs.id"],
            ondelete="RESTRICT",
            name="fk_analytics_data_version_refresh_same_tenant",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    current_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cache_namespace: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    freshness_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    last_refresh_job_id: Mapped[UUID | None] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AnalyticsLineage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "analytics_lineage"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "fact_id",
            "canonical_table",
            "canonical_record_id",
            name="uq_analytics_lineage_edge",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "fact_id"],
            ["analytics_facts.tenant_id", "analytics_facts.id"],
            ondelete="CASCADE",
            name="fk_analytics_lineage_fact_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="RESTRICT",
            name="fk_analytics_lineage_batch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "refresh_job_id"],
            ["analytics_refresh_jobs.tenant_id", "analytics_refresh_jobs.id"],
            ondelete="CASCADE",
            name="fk_analytics_lineage_refresh_same_tenant",
        ),
        Index("ix_analytics_lineage_fact", "tenant_id", "fact_id"),
        Index("ix_analytics_lineage_source", "tenant_id", "canonical_table", "canonical_record_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    fact_id: Mapped[UUID] = mapped_column()
    source_batch_id: Mapped[UUID | None] = mapped_column()
    canonical_table: Mapped[str] = mapped_column(String(100), nullable=False)
    canonical_record_id: Mapped[str] = mapped_column(String(300), nullable=False)
    canonical_version: Mapped[str] = mapped_column(String(100), nullable=False)
    transformation_version: Mapped[str] = mapped_column(String(40), nullable=False)
    refresh_job_id: Mapped[UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AnalyticsGoal(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "analytics_goals"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_analytics_goals_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_analytics_goals_company_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_analytics_goals_branch_same_tenant",
        ),
        CheckConstraint("period_end >= period_start", name="ck_analytics_goals_period"),
        CheckConstraint(
            "lower_value IS NULL OR upper_value IS NULL OR upper_value >= lower_value",
            name="ck_analytics_goals_range",
        ),
        Index("ix_analytics_goals_lookup", "tenant_id", "kpi_code", "period_start", "period_end"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID | None] = mapped_column()
    branch_id: Mapped[UUID | None] = mapped_column()
    kpi_code: Mapped[str] = mapped_column(String(140), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    target_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    lower_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    upper_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    direction: Mapped[str] = mapped_column(String(24), nullable=False)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    note: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AnalyticsGoalHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "analytics_goal_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "goal_id"],
            ["analytics_goals.tenant_id", "analytics_goals.id"],
            ondelete="CASCADE",
            name="fk_analytics_goal_history_goal_same_tenant",
        ),
        Index("ix_analytics_goal_history_goal", "tenant_id", "goal_id", "changed_at"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    goal_id: Mapped[UUID] = mapped_column()
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    changed_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    change_reason: Mapped[str | None] = mapped_column(String(500))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
