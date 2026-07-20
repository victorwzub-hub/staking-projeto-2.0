"""Create the tenant-safe analytical warehouse and semantic layer.

Revision ID: 20260718_0004
Revises: 20260717_0003
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260718_0004"
down_revision: str | None = "20260717_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)

ANALYTICS_PERMISSIONS: tuple[tuple[str, str, str], ...] = (
    ("analytics.view", "company", "Visualizar analytics e indicadores operacionais"),
    ("analytics.financial", "company", "Visualizar indicadores financeiros e de margem"),
    ("analytics.goals.manage", "company", "Configurar e versionar metas analíticas"),
    ("analytics.export", "company", "Exportar resultados analíticos autorizados"),
    ("analytics.detail", "company", "Visualizar drill-down e lineage detalhado"),
    ("analytics.catalog.admin", "tenant", "Administrar o catálogo semântico versionado"),
    ("analytics.recompute", "company", "Recomputar indicadores por janela"),
    ("analytics.backfill", "tenant", "Executar backfill analítico controlado"),
)

_ALL_PERMISSION_KEYS = tuple(key for key, _, _ in ANALYTICS_PERMISSIONS)
ROLE_PERMISSION_GRANTS: dict[str, tuple[str, ...]] = {
    "tenant_owner": _ALL_PERMISSION_KEYS,
    "tenant_admin": _ALL_PERMISSION_KEYS,
    "company_admin": _ALL_PERMISSION_KEYS,
    "branch_manager": (
        "analytics.view",
        "analytics.financial",
        "analytics.goals.manage",
        "analytics.export",
        "analytics.detail",
        "analytics.recompute",
    ),
    "analyst": (
        "analytics.view",
        "analytics.financial",
        "analytics.export",
        "analytics.detail",
    ),
    "consultant": (
        "analytics.view",
        "analytics.financial",
        "analytics.export",
        "analytics.detail",
    ),
    "accountant": ("analytics.view", "analytics.financial", "analytics.export"),
    "viewer": ("analytics.view",),
}

TENANT_TABLES = (
    "analytics_dimensions",
    "analytics_facts",
    "analytics_daily_aggregates",
    "analytics_kpi_definition_versions",
    "analytics_kpi_results",
    "analytics_refresh_jobs",
    "analytics_data_versions",
    "analytics_lineage",
    "analytics_goals",
    "analytics_goal_history",
)


def _uuid(kind: str, value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"pharma-intelligence:{kind}:{value}"))


def _enable_rls(table: str) -> None:
    expression = (
        "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
        "OR current_setting('app.is_platform_admin', true) = 'true'"
    )
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY "{table}_tenant_policy" ON "{table}" '
        f"USING ({expression}) WITH CHECK ({expression})"
    )


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.create_table(
        "analytics_dimensions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("dimension_type", sa.String(40), nullable=False),
        sa.Column("natural_key", sa.String(300), nullable=False),
        sa.Column("source_record_id", sa.String(300)),
        sa.Column("parent_natural_key", sa.String(300)),
        sa.Column("label", sa.String(300), nullable=False),
        sa.Column(
            "attributes", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *_timestamps(),
        sa.UniqueConstraint(
            "tenant_id",
            "dimension_type",
            "natural_key",
            "effective_from",
            name="uq_analytics_dimensions_version",
        ),
        sa.CheckConstraint(
            "dimension_type IN ('date','hour','tenant','economic_group','company','branch','product','product_identifier','category','category_hierarchy','brand','manufacturer','supplier','channel','payment_method','sale_origin','movement_type','promotion','price_band','commercial_classification')",
            name="ck_analytics_dimensions_type",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_analytics_dimensions_period",
        ),
    )
    op.create_index(
        "ix_analytics_dimensions_lookup",
        "analytics_dimensions",
        ["tenant_id", "dimension_type", "natural_key"],
    )
    op.create_index(
        "uq_analytics_dimensions_current",
        "analytics_dimensions",
        ["tenant_id", "dimension_type", "natural_key"],
        unique=True,
        postgresql_where=sa.text("current = true"),
    )

    op.create_table(
        "analytics_facts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("fact_type", sa.String(40), nullable=False),
        sa.Column("grain_key", sa.String(500), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date_value", sa.Date(), nullable=False),
        sa.Column("hour_value", sa.Integer()),
        sa.Column("company_id", UUID),
        sa.Column("branch_id", UUID),
        sa.Column("product_id", UUID),
        sa.Column("category_id", UUID),
        sa.Column("supplier_id", UUID),
        sa.Column("channel", sa.String(60)),
        sa.Column("payment_method", sa.String(60)),
        sa.Column("movement_type", sa.String(40)),
        sa.Column("promotion_id", UUID),
        sa.Column("batch_id", UUID),
        sa.Column("canonical_table", sa.String(100), nullable=False),
        sa.Column("canonical_record_id", sa.String(300), nullable=False),
        sa.Column("canonical_version", sa.String(100), nullable=False),
        sa.Column(
            "measures", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "dimension_snapshot",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_version", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_analytics_facts_tenant_id"),
        sa.UniqueConstraint("tenant_id", "fact_type", "grain_key", name="uq_analytics_facts_grain"),
        sa.CheckConstraint(
            "fact_type IN ('sale','sale_item','payment','return','purchase','purchase_item','receipt','inventory_movement','stock_snapshot','price','promotion','cost','data_quality','import_execution')",
            name="ck_analytics_facts_type",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_analytics_facts_company_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_analytics_facts_branch_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            ondelete="RESTRICT",
            name="fk_analytics_facts_product_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["canonical_categories.tenant_id", "canonical_categories.id"],
            ondelete="RESTRICT",
            name="fk_analytics_facts_category_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["canonical_suppliers.tenant_id", "canonical_suppliers.id"],
            ondelete="RESTRICT",
            name="fk_analytics_facts_supplier_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "promotion_id"],
            ["canonical_promotions.tenant_id", "canonical_promotions.id"],
            ondelete="RESTRICT",
            name="fk_analytics_facts_promotion_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="RESTRICT",
            name="fk_analytics_facts_batch_same_tenant",
        ),
    )
    op.create_index(
        "ix_analytics_facts_scope_date",
        "analytics_facts",
        ["tenant_id", "company_id", "branch_id", "date_value", "fact_type"],
    )
    op.create_index(
        "ix_analytics_facts_product_date",
        "analytics_facts",
        ["tenant_id", "product_id", "date_value"],
    )
    op.create_index(
        "ix_analytics_facts_supplier_date",
        "analytics_facts",
        ["tenant_id", "supplier_id", "date_value"],
    )
    op.create_index(
        "ix_analytics_facts_date_brin", "analytics_facts", ["occurred_at"], postgresql_using="brin"
    )

    op.create_table(
        "analytics_daily_aggregates",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("date_value", sa.Date(), nullable=False),
        sa.Column("grain", sa.String(40), nullable=False),
        sa.Column("company_id", UUID),
        sa.Column("branch_id", UUID),
        sa.Column("product_id", UUID),
        sa.Column("category_id", UUID),
        sa.Column("supplier_id", UUID),
        sa.Column("dimension_value", sa.String(300)),
        sa.Column(
            "measures", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("source_max_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_version", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_analytics_aggregate_company_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_analytics_aggregate_branch_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            ondelete="RESTRICT",
            name="fk_analytics_aggregate_product_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["canonical_categories.tenant_id", "canonical_categories.id"],
            ondelete="RESTRICT",
            name="fk_analytics_aggregate_category_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["canonical_suppliers.tenant_id", "canonical_suppliers.id"],
            ondelete="RESTRICT",
            name="fk_analytics_aggregate_supplier_same_tenant",
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_analytics_daily_aggregate_grain ON analytics_daily_aggregates (tenant_id,date_value,grain,company_id,branch_id,product_id,category_id,supplier_id,dimension_value) NULLS NOT DISTINCT"
    )
    op.create_index(
        "ix_analytics_daily_aggregate_query",
        "analytics_daily_aggregates",
        ["tenant_id", "grain", "date_value", "company_id", "branch_id"],
    )
    op.create_index(
        "ix_analytics_daily_aggregate_date_brin",
        "analytics_daily_aggregates",
        ["date_value"],
        postgresql_using="brin",
    )

    op.create_table(
        "analytics_kpi_definition_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kpi_code", sa.String(140), nullable=False),
        sa.Column("formula_version", sa.Integer(), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column("definition_hash", sa.String(64), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "kpi_code", "formula_version", name="uq_analytics_kpi_version"
        ),
    )
    op.create_index(
        "ix_analytics_kpi_catalog",
        "analytics_kpi_definition_versions",
        ["tenant_id", "category", "status", "kpi_code"],
    )

    op.create_table(
        "analytics_kpi_results",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kpi_code", sa.String(140), nullable=False),
        sa.Column("formula_version", sa.Integer(), nullable=False),
        sa.Column("scope_hash", sa.String(64), nullable=False),
        sa.Column("filters", postgresql.JSONB(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(24, 6)),
        sa.Column("reason", sa.String(80)),
        sa.Column(
            "comparison", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("freshness_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_version", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "kpi_code",
            "formula_version",
            "scope_hash",
            "period_start",
            "period_end",
            "data_version",
            name="uq_analytics_kpi_result_version",
        ),
    )
    op.create_index(
        "ix_analytics_kpi_results_lookup",
        "analytics_kpi_results",
        ["tenant_id", "kpi_code", "period_end"],
    )

    op.create_table(
        "analytics_refresh_jobs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("trigger_type", sa.String(32), nullable=False),
        sa.Column("source_batch_id", UUID),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column("state", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("watermark_before", sa.DateTime(timezone=True)),
        sa.Column("watermark_after", sa.DateTime(timezone=True)),
        sa.Column(
            "checkpoint", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "metrics", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(120)),
        sa.Column("error_message", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "id", name="uq_analytics_refresh_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_analytics_refresh_idempotency"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="RESTRICT",
            name="fk_analytics_refresh_batch_same_tenant",
        ),
        sa.CheckConstraint(
            "state IN ('queued','running','completed','failed','cancelled')",
            name="ck_analytics_refresh_state",
        ),
        sa.CheckConstraint("window_end >= window_start", name="ck_analytics_refresh_window"),
    )
    op.create_index(
        "uq_analytics_refresh_running",
        "analytics_refresh_jobs",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("state = 'running'"),
    )
    op.create_index("ix_analytics_refresh_queue", "analytics_refresh_jobs", ["state", "created_at"])

    op.create_table(
        "analytics_data_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("current_version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_namespace", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("watermark", sa.DateTime(timezone=True)),
        sa.Column("freshness_at", sa.DateTime(timezone=True)),
        sa.Column("quality_score", sa.Numeric(7, 4)),
        sa.Column("last_refresh_job_id", UUID),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_analytics_data_versions_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "last_refresh_job_id"],
            ["analytics_refresh_jobs.tenant_id", "analytics_refresh_jobs.id"],
            ondelete="RESTRICT",
            name="fk_analytics_data_version_refresh_same_tenant",
        ),
    )

    op.create_table(
        "analytics_lineage",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("fact_id", UUID, nullable=False),
        sa.Column("source_batch_id", UUID),
        sa.Column("canonical_table", sa.String(100), nullable=False),
        sa.Column("canonical_record_id", sa.String(300), nullable=False),
        sa.Column("canonical_version", sa.String(100), nullable=False),
        sa.Column("transformation_version", sa.String(40), nullable=False),
        sa.Column("refresh_job_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "fact_id",
            "canonical_table",
            "canonical_record_id",
            name="uq_analytics_lineage_edge",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "fact_id"],
            ["analytics_facts.tenant_id", "analytics_facts.id"],
            ondelete="CASCADE",
            name="fk_analytics_lineage_fact_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="RESTRICT",
            name="fk_analytics_lineage_batch_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "refresh_job_id"],
            ["analytics_refresh_jobs.tenant_id", "analytics_refresh_jobs.id"],
            ondelete="CASCADE",
            name="fk_analytics_lineage_refresh_same_tenant",
        ),
    )
    op.create_index("ix_analytics_lineage_fact", "analytics_lineage", ["tenant_id", "fact_id"])
    op.create_index(
        "ix_analytics_lineage_source",
        "analytics_lineage",
        ["tenant_id", "canonical_table", "canonical_record_id"],
    )

    op.create_table(
        "analytics_goals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("company_id", UUID),
        sa.Column("branch_id", UUID),
        sa.Column("kpi_code", sa.String(140), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("target_value", sa.Numeric(24, 6)),
        sa.Column("lower_value", sa.Numeric(24, 6)),
        sa.Column("upper_value", sa.Numeric(24, 6)),
        sa.Column("direction", sa.String(24), nullable=False),
        sa.Column(
            "owner_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("note", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "id", name="uq_analytics_goals_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_analytics_goals_company_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_analytics_goals_branch_same_tenant",
        ),
        sa.CheckConstraint("period_end >= period_start", name="ck_analytics_goals_period"),
        sa.CheckConstraint(
            "lower_value IS NULL OR upper_value IS NULL OR upper_value >= lower_value",
            name="ck_analytics_goals_range",
        ),
    )
    op.create_index(
        "ix_analytics_goals_lookup",
        "analytics_goals",
        ["tenant_id", "kpi_code", "period_start", "period_end"],
    )

    op.create_table(
        "analytics_goal_history",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("goal_id", UUID, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "changed_by_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("change_reason", sa.String(500)),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "goal_id"],
            ["analytics_goals.tenant_id", "analytics_goals.id"],
            ondelete="CASCADE",
            name="fk_analytics_goal_history_goal_same_tenant",
        ),
    )
    op.create_index(
        "ix_analytics_goal_history_goal",
        "analytics_goal_history",
        ["tenant_id", "goal_id", "changed_at"],
    )

    permission_table = sa.table(
        "permissions",
        sa.column("id", UUID),
        sa.column("key", sa.String()),
        sa.column("scope", sa.String()),
        sa.column("description", sa.String()),
        sa.column("catalog_version", sa.Integer()),
    )
    op.bulk_insert(
        permission_table,
        [
            {
                "id": _uuid("permission", key),
                "key": key,
                "scope": scope,
                "description": description,
                "catalog_version": 3,
            }
            for key, scope, description in ANALYTICS_PERMISSIONS
        ],
    )
    op.execute("ALTER TABLE role_permissions DISABLE TRIGGER role_permissions_protect_system")
    for role_slug, keys in ROLE_PERMISSION_GRANTS.items():
        keys_sql = ",".join(f"'{key}'" for key in keys)
        op.execute(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT role.id, permission.id FROM roles AS role CROSS JOIN permissions AS permission "
            f"WHERE role.slug = '{role_slug}' AND role.is_system = true AND permission.key IN ({keys_sql}) "
            "ON CONFLICT DO NOTHING"
        )
    op.execute("ALTER TABLE role_permissions ENABLE TRIGGER role_permissions_protect_system")

    for table in TENANT_TABLES:
        _enable_rls(table)


def downgrade() -> None:
    op.execute("ALTER TABLE role_permissions DISABLE TRIGGER role_permissions_protect_system")
    keys_sql = ",".join(f"'{key}'" for key in _ALL_PERMISSION_KEYS)
    op.execute(
        f"DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE key IN ({keys_sql}))"
    )
    op.execute(f"DELETE FROM permissions WHERE key IN ({keys_sql})")
    op.execute("ALTER TABLE role_permissions ENABLE TRIGGER role_permissions_protect_system")
    op.drop_table("analytics_goal_history")
    op.drop_table("analytics_goals")
    op.drop_table("analytics_lineage")
    op.drop_table("analytics_data_versions")
    op.drop_table("analytics_refresh_jobs")
    op.drop_table("analytics_kpi_results")
    op.drop_table("analytics_kpi_definition_versions")
    op.drop_table("analytics_daily_aggregates")
    op.drop_table("analytics_facts")
    op.drop_table("analytics_dimensions")
