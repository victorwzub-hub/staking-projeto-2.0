"""Create the canonical data platform and ERP integration foundation.

Revision ID: 20260717_0003
Revises: 20260717_0002
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260717_0003"
down_revision: str | None = "20260717_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)

INTEGRATION_PERMISSIONS: tuple[tuple[str, str, str], ...] = (
    ("integration.view", "company", "Visualizar integrações e dados canônicos"),
    ("integration.create", "company", "Criar integrações e fontes de dados"),
    ("integration.edit", "company", "Editar e ativar integrações"),
    ("integration.test", "company", "Testar conexão de integrações"),
    ("integration.sync", "company", "Iniciar sincronizações e importações"),
    ("integration.cancel", "company", "Cancelar sincronizações"),
    ("integration.reprocess", "company", "Reprocessar lotes e dead letters"),
    ("integration.raw", "company", "Visualizar payload bruto no landing"),
    ("integration.errors", "company", "Visualizar erros e rejeições"),
    ("integration.mapping", "company", "Administrar mapeamentos versionados"),
    ("integration.quality", "company", "Visualizar qualidade dos dados"),
    ("integration.correct", "company", "Corrigir registros rejeitados"),
    ("integration.export", "company", "Exportar relatórios de integração"),
)

_ALL_INTEGRATION_PERMISSION_KEYS = tuple(key for key, _, _ in INTEGRATION_PERMISSIONS)
ROLE_PERMISSION_GRANTS: dict[str, tuple[str, ...]] = {
    "tenant_owner": _ALL_INTEGRATION_PERMISSION_KEYS,
    "tenant_admin": _ALL_INTEGRATION_PERMISSION_KEYS,
    "company_admin": _ALL_INTEGRATION_PERMISSION_KEYS,
    "branch_manager": (
        "integration.view",
        "integration.test",
        "integration.sync",
        "integration.cancel",
        "integration.reprocess",
        "integration.errors",
        "integration.quality",
        "integration.correct",
        "integration.export",
    ),
    "analyst": (
        "integration.view",
        "integration.errors",
        "integration.quality",
        "integration.export",
    ),
    "consultant": (
        "integration.view",
        "integration.errors",
        "integration.quality",
        "integration.export",
    ),
    "accountant": (
        "integration.view",
        "integration.quality",
        "integration.export",
    ),
    "viewer": ("integration.view", "integration.quality"),
}

QUALITY_RULES: tuple[tuple[str, str], ...] = (
    ("required_field", "blocking"),
    ("invalid_type", "blocking"),
    ("invalid_date", "blocking"),
    ("unexpected_negative", "blocking"),
    ("incompatible_quantity", "blocking"),
    ("missing_reference", "blocking"),
    ("unmapped_product", "blocking"),
    ("missing_branch", "blocking"),
    ("missing_supplier", "blocking"),
    ("duplicate_identifier", "warning"),
    ("sale_without_item", "blocking"),
    ("total_mismatch", "blocking"),
    ("payment_mismatch", "error"),
    ("missing_cost", "warning"),
    ("impossible_balance", "blocking"),
    ("out_of_order_movement", "warning"),
    ("overlapping_period", "blocking"),
    ("stale_data", "warning"),
    ("volume_anomaly", "warning"),
    ("probable_duplicate", "warning"),
)

TENANT_TABLES: tuple[str, ...] = (
    "canonical_brands",
    "canonical_categories",
    "canonical_inventory_lots",
    "canonical_inventory_movements",
    "canonical_manufacturers",
    "canonical_product_identifiers",
    "canonical_product_presentations",
    "canonical_product_prices",
    "canonical_products",
    "canonical_promotion_products",
    "canonical_promotions",
    "canonical_purchase_items",
    "canonical_purchase_orders",
    "canonical_purchase_receipts",
    "canonical_sale_adjustments",
    "canonical_sale_items",
    "canonical_sale_payments",
    "canonical_sales",
    "canonical_stock_balances",
    "canonical_stock_snapshots",
    "canonical_supplier_costs",
    "canonical_supplier_identifiers",
    "canonical_supplier_products",
    "canonical_suppliers",
    "connector_instances",
    "credential_references",
    "data_sources",
    "field_mappings",
    "import_batches",
    "imported_files",
    "integration_dead_letters",
    "integration_inbox_messages",
    "integration_outbox_events",
    "landing_manifests",
    "lineage_events",
    "mapping_profiles",
    "mapping_versions",
    "processing_errors",
    "processing_leases",
    "processing_state_transitions",
    "processing_statistics",
    "processing_steps",
    "quality_results",
    "rejected_records",
    "staging_records",
    "sync_attempts",
    "sync_checkpoints",
    "sync_cursors",
    "sync_executions",
    "webhook_receipts",
)


def _uuid(kind: str, value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"pharma-intelligence:{kind}:{value}"))


def _enable_rls(table: str, *, using: str | None = None, check: str | None = None) -> None:
    tenant_expression = (
        "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
        "OR current_setting('app.is_platform_admin', true) = 'true'"
    )
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY "{table}_tenant_policy" ON "{table}" '
        f"USING ({using or tenant_expression}) WITH CHECK ({check or tenant_expression})"
    )


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "connector_definitions",
        sa.Column("connector_key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("schema_version", sa.String(length=40), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("authentication_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("supported_entities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "status IN ('active','deprecated','disabled')", name="ck_connector_definitions_status"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connector_key", "version", name="uq_connector_definitions_key_version"
        ),
    )
    op.create_table(
        "canonical_brands",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("normalized_name", sa.String(length=180), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_canonical_brands_tenant_id"),
        sa.UniqueConstraint("tenant_id", "normalized_name", name="uq_canonical_brands_name"),
    )
    op.create_table(
        "canonical_categories",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("normalized_name", sa.String(length=180), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["canonical_categories.tenant_id", "canonical_categories.id"],
            name="fk_canonical_categories_parent_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_canonical_categories_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "parent_id", "normalized_name", name="uq_canonical_categories_path"
        ),
    )
    op.create_index(
        "ix_canonical_categories_parent",
        "canonical_categories",
        ["tenant_id", "parent_id"],
        unique=False,
    )
    op.create_table(
        "canonical_manufacturers",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=220), nullable=False),
        sa.Column("normalized_name", sa.String(length=220), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_canonical_manufacturers_tenant_id"),
        sa.UniqueConstraint("tenant_id", "normalized_name", name="uq_canonical_manufacturers_name"),
    )
    op.create_table(
        "integration_outbox_events",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("aggregate_type", sa.String(length=60), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_attempts", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_integration_outbox_idempotency"
        ),
    )
    op.create_index(
        "ix_integration_outbox_pending",
        "integration_outbox_events",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_table(
        "processing_leases",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.String(length=180), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "resource_type", "resource_id", name="uq_processing_leases_resource"
        ),
    )
    op.create_index(
        "ix_processing_leases_expiry", "processing_leases", ["lease_until"], unique=False
    )
    op.create_table(
        "processing_state_transitions",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("from_state", sa.String(length=40), nullable=False),
        sa.Column("to_state", sa.String(length=40), nullable=False),
        sa.Column("actor_type", sa.String(length=24), nullable=False),
        sa.Column("actor_id", sa.String(length=160), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_processing_state_transitions_resource",
        "processing_state_transitions",
        ["tenant_id", "resource_type", "resource_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "quality_rules",
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("rule_key", sa.String(length=140), nullable=False),
        sa.Column("rule_type", sa.String(length=60), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=True),
        sa.Column("severity", sa.String(length=24), nullable=False),
        sa.Column("configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("is_platform_rule", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "severity IN ('informational','warning','error','blocking')",
            name="ck_quality_rules_severity",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_quality_rules_platform_key",
        "quality_rules",
        ["rule_key"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )
    op.create_index(
        "uq_quality_rules_tenant_key",
        "quality_rules",
        ["tenant_id", "rule_key"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.create_table(
        "credential_references",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("secret_identifier", sa.String(length=500), nullable=False),
        sa.Column("display_hint", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "status IN ('active','rotating','revoked')", name="ck_credential_references_status"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_credential_references_branch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            name="fk_credential_references_company_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_credential_references_tenant_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_credential_references_tenant_name"),
    )
    op.create_index(
        "ix_credential_references_scope",
        "credential_references",
        ["tenant_id", "company_id", "branch_id"],
        unique=False,
    )
    op.create_table(
        "connector_instances",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("connector_definition_id", sa.Uuid(), nullable=False),
        sa.Column("credential_reference_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_health_status", sa.String(length=24), nullable=True),
        sa.Column("last_health_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','active','inactive','error')", name="ck_connector_instances_status"
        ),
        sa.ForeignKeyConstraint(
            ["connector_definition_id"], ["connector_definitions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_connector_instances_branch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            name="fk_connector_instances_company_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "credential_reference_id"],
            ["credential_references.tenant_id", "credential_references.id"],
            name="fk_connector_instances_credential_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_connector_instances_tenant_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_connector_instances_tenant_name"),
    )
    op.create_index(
        "ix_connector_instances_scope",
        "connector_instances",
        ["tenant_id", "company_id", "branch_id"],
        unique=False,
    )
    op.create_table(
        "data_sources",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("connector_instance_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("dataset_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("sync_mode", sa.String(length=24), nullable=False),
        sa.Column("schedule_cron", sa.String(length=100), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "status IN ('active','inactive','error')", name="ck_data_sources_status"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_data_sources_branch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            name="fk_data_sources_company_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "connector_instance_id"],
            ["connector_instances.tenant_id", "connector_instances.id"],
            name="fk_data_sources_instance_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_data_sources_tenant_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_data_sources_tenant_name"),
    )
    op.create_index(
        "ix_data_sources_scope_status",
        "data_sources",
        ["tenant_id", "company_id", "branch_id", "status"],
        unique=False,
    )
    op.create_table(
        "integration_inbox_messages",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("external_message_id", sa.String(length=240), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            name="fk_integration_inbox_source_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "external_message_id",
            name="uq_integration_inbox_external",
        ),
    )
    op.create_table(
        "mapping_profiles",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("dataset_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','published','archived')", name="ck_mapping_profiles_status"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            name="fk_mapping_profiles_source_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "data_source_id", "name", name="uq_mapping_profiles_source_name"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mapping_profiles_tenant_id"),
    )
    op.create_table(
        "sync_cursors",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("cursor_key", sa.String(length=120), nullable=False),
        sa.Column("cursor_value", sa.Text(), nullable=True),
        sa.Column("source_version", sa.String(length=100), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            name="fk_sync_cursors_source_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "data_source_id", "cursor_key", name="uq_sync_cursors_source_key"
        ),
    )
    op.create_table(
        "webhook_receipts",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("external_event_id", sa.String(length=240), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=900), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            name="fk_webhook_receipts_source_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "data_source_id", "external_event_id", name="uq_webhook_receipts_external"
        ),
    )
    op.create_table(
        "mapping_versions",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mapping_profile_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("connector_version", sa.String(length=40), nullable=False),
        sa.Column("source_schema_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "status IN ('draft','validated','published','retired')",
            name="ck_mapping_versions_status",
        ),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mapping_profile_id"],
            ["mapping_profiles.tenant_id", "mapping_profiles.id"],
            name="fk_mapping_versions_profile_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mapping_versions_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "mapping_profile_id",
            "version_number",
            name="uq_mapping_versions_profile_number",
        ),
    )
    op.create_table(
        "field_mappings",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mapping_version_id", sa.Uuid(), nullable=False),
        sa.Column("source_field", sa.String(length=200), nullable=False),
        sa.Column("target_entity", sa.String(length=60), nullable=False),
        sa.Column("target_field", sa.String(length=120), nullable=False),
        sa.Column("transform_type", sa.String(length=24), nullable=False),
        sa.Column("transform_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("default_value", sa.String(length=500), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "transform_type IN ('identity','trim','uppercase','lowercase','decimal','integer','date','datetime','boolean','constant')",
            name="ck_field_mappings_transform",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mapping_version_id"],
            ["mapping_versions.tenant_id", "mapping_versions.id"],
            name="fk_field_mappings_version_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "mapping_version_id", "source_field", name="uq_field_mappings_source_field"
        ),
    )
    op.create_table(
        "import_batches",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("mapping_version_id", sa.Uuid(), nullable=True),
        sa.Column("parent_batch_id", sa.Uuid(), nullable=True),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("dataset_type", sa.String(length=40), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("received_records", sa.BigInteger(), nullable=False),
        sa.Column("valid_records", sa.BigInteger(), nullable=False),
        sa.Column("rejected_records", sa.BigInteger(), nullable=False),
        sa.Column("duplicate_records", sa.BigInteger(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "state IN ('created','queued','connecting','extracting','received','validating','mapping','normalizing','loading','completed','completed_with_warnings','failed','cancelled','quarantined','retry_scheduled')",
            name="ck_import_batches_state",
        ),
        sa.CheckConstraint("progress_percent BETWEEN 0 AND 100", name="ck_import_batches_progress"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_import_batches_branch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            name="fk_import_batches_company_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            name="fk_import_batches_source_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mapping_version_id"],
            ["mapping_versions.tenant_id", "mapping_versions.id"],
            name="fk_import_batches_mapping_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_import_batches_parent_same_tenant",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "idempotency_key",
            name="uq_import_batches_source_idempotency",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_import_batches_tenant_id"),
    )
    op.create_index(
        "ix_import_batches_active",
        "import_batches",
        ["tenant_id", "state"],
        unique=False,
        postgresql_where=sa.text(
            "state NOT IN ('completed','completed_with_warnings','cancelled')"
        ),
    )
    op.create_index(
        "ix_import_batches_scope_created",
        "import_batches",
        ["tenant_id", "company_id", "branch_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "canonical_promotions",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=240), nullable=False),
        sa.Column("source_version", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=220), nullable=False),
        sa.Column("discount_type", sa.String(length=24), nullable=False),
        sa.Column("discount_value", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decision_source", sa.String(length=60), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "discount_type IN ('percentage','fixed','price','quantity')",
            name="ck_canonical_promotions_discount_type",
        ),
        sa.CheckConstraint("valid_to > valid_from", name="ck_canonical_promotions_period"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_canonical_promotions_batch_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_canonical_promotions_branch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            name="fk_canonical_promotions_company_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            name="fk_canonical_promotions_source_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "external_id",
            name="uq_canonical_promotions_source_external",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_canonical_promotions_tenant_id"),
    )
    op.create_table(
        "imported_files",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("object_bucket", sa.String(length=120), nullable=False),
        sa.Column("object_key", sa.String(length=900), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("immutable", sa.Boolean(), nullable=False),
        sa.Column("retention_until", sa.Date(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint("size_bytes >= 0", name="ck_imported_files_size"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_imported_files_batch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            name="fk_imported_files_source_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
        sa.UniqueConstraint(
            "tenant_id", "data_source_id", "content_sha256", name="uq_imported_files_source_hash"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_imported_files_tenant_id"),
    )
    op.create_index(
        "ix_imported_files_retention", "imported_files", ["retention_until"], unique=False
    )
    op.create_table(
        "processing_statistics",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("step_name", sa.String(length=60), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("received_count", sa.BigInteger(), nullable=False),
        sa.Column("valid_count", sa.BigInteger(), nullable=False),
        sa.Column("rejected_count", sa.BigInteger(), nullable=False),
        sa.Column("duplicate_count", sa.BigInteger(), nullable=False),
        sa.Column("bytes_received", sa.BigInteger(), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("records_per_second", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_processing_statistics_batch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "batch_id",
            "step_name",
            "entity_type",
            name="uq_processing_statistics_step_entity",
        ),
    )
    op.create_table(
        "quality_results",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("quality_rule_id", sa.Uuid(), nullable=True),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("rule_key", sa.String(length=140), nullable=False),
        sa.Column("severity", sa.String(length=24), nullable=False),
        sa.Column("evaluated_records", sa.BigInteger(), nullable=False),
        sa.Column("failed_records", sa.BigInteger(), nullable=False),
        sa.Column("score", sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["quality_rule_id"], ["quality_rules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_quality_results_batch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_quality_results_batch_entity",
        "quality_results",
        ["tenant_id", "batch_id", "entity_type"],
        unique=False,
    )
    op.create_table(
        "staging_records",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("external_id", sa.String(length=240), nullable=False),
        sa.Column("source_version", sa.String(length=100), nullable=False),
        sa.Column("row_number", sa.BigInteger(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("normalized_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "status IN ('received','valid','rejected','duplicate','loaded')",
            name="ck_staging_records_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_staging_records_batch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            name="fk_staging_records_source_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "batch_id",
            "entity_type",
            "external_id",
            "source_version",
            name="uq_staging_records_batch_identity",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_staging_records_tenant_id"),
    )
    op.create_index(
        "ix_staging_records_batch_status",
        "staging_records",
        ["tenant_id", "batch_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_staging_records_occurred_brin",
        "staging_records",
        ["occurred_at"],
        unique=False,
        postgresql_using="brin",
    )
    op.create_table(
        "sync_executions",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("mode", sa.String(length=24), nullable=False),
        sa.Column("request_options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("range_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("range_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "state IN ('created','queued','connecting','extracting','received','validating','mapping','normalizing','loading','completed','completed_with_warnings','failed','cancelled','quarantined','retry_scheduled')",
            name="ck_sync_executions_state",
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_sync_executions_batch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            name="fk_sync_executions_source_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "idempotency_key",
            name="uq_sync_executions_source_idempotency",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_sync_executions_tenant_id"),
    )
    op.create_index(
        "ix_sync_executions_source_created",
        "sync_executions",
        ["tenant_id", "data_source_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "canonical_products",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("staging_record_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=240), nullable=False),
        sa.Column("source_version", sa.String(length=100), nullable=False),
        sa.Column("sku", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("normalized_name", sa.String(length=300), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=True),
        sa.Column("manufacturer_id", sa.Uuid(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("base_unit", sa.String(length=24), nullable=False),
        sa.Column("commercial_status", sa.String(length=24), nullable=False),
        sa.Column("commercial_classification", sa.String(length=100), nullable=True),
        sa.Column("regulatory_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("controlled_attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "commercial_status IN ('active','inactive','discontinued','blocked')",
            name="ck_canonical_products_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_canonical_products_batch_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "brand_id"],
            ["canonical_brands.tenant_id", "canonical_brands.id"],
            name="fk_canonical_products_brand_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["canonical_categories.tenant_id", "canonical_categories.id"],
            name="fk_canonical_products_category_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_canonical_products_branch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            name="fk_canonical_products_company_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            name="fk_canonical_products_source_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "manufacturer_id"],
            ["canonical_manufacturers.tenant_id", "canonical_manufacturers.id"],
            name="fk_canonical_products_manufacturer_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            name="fk_canonical_products_staging_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "external_id",
            name="uq_canonical_products_source_external",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_canonical_products_tenant_id"),
    )
    op.create_index(
        "ix_canonical_products_scope_name",
        "canonical_products",
        ["tenant_id", "company_id", "branch_id", "normalized_name"],
        unique=False,
    )
    op.create_table(
        "canonical_sales",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("staging_record_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=240), nullable=False),
        sa.Column("source_version", sa.String(length=100), nullable=False),
        sa.Column("accounting_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("operator_external_id", sa.String(length=160), nullable=True),
        sa.Column("customer_pseudonym", sa.String(length=64), nullable=True),
        sa.Column("gross_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("discount_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("tax_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("net_total", sa.Numeric(precision=18, scale=4), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "gross_total >= 0 AND discount_total >= 0 AND net_total >= 0",
            name="ck_canonical_sales_totals",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_canonical_sales_batch_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_canonical_sales_branch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            name="fk_canonical_sales_source_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            name="fk_canonical_sales_staging_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", "occurred_at"),
        sa.UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "external_id",
            "occurred_at",
            name="uq_canonical_sales_source_external",
        ),
        sa.UniqueConstraint(
            "tenant_id", "id", "occurred_at", name="uq_canonical_sales_tenant_id_occurred"
        ),
        postgresql_partition_by="RANGE (occurred_at)",
    )
    op.create_index(
        "ix_canonical_sales_occurred_brin",
        "canonical_sales",
        ["occurred_at"],
        unique=False,
        postgresql_using="brin",
    )
    op.create_index(
        "ix_canonical_sales_scope_occurred",
        "canonical_sales",
        ["tenant_id", "company_id", "branch_id", "occurred_at"],
        unique=False,
    )
    op.create_table(
        "canonical_suppliers",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("staging_record_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=240), nullable=False),
        sa.Column("source_version", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=260), nullable=False),
        sa.Column("normalized_name", sa.String(length=260), nullable=False),
        sa.Column("tax_id_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("commercial_terms", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_canonical_suppliers_batch_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            name="fk_canonical_suppliers_company_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            name="fk_canonical_suppliers_source_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            name="fk_canonical_suppliers_staging_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "external_id",
            name="uq_canonical_suppliers_source_external",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_canonical_suppliers_tenant_id"),
    )
    op.create_index(
        "ix_canonical_suppliers_scope_name",
        "canonical_suppliers",
        ["tenant_id", "company_id", "normalized_name"],
        unique=False,
    )
    op.create_table(
        "integration_dead_letters",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("step_name", sa.String(length=60), nullable=False),
        sa.Column("error_class", sa.String(length=60), nullable=False),
        sa.Column("reason", sa.String(length=800), nullable=False),
        sa.Column("payload_reference", sa.String(length=900), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "status IN ('open','replayed','discarded')", name="ck_integration_dead_letters_status"
        ),
        sa.ForeignKeyConstraint(["execution_id"], ["sync_executions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_integration_dead_letters_batch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_integration_dead_letters_status",
        "integration_dead_letters",
        ["tenant_id", "status", "created_at"],
        unique=False,
    )
    op.create_table(
        "landing_manifests",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("imported_file_id", sa.Uuid(), nullable=False),
        sa.Column("record_count", sa.BigInteger(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("connector_version", sa.String(length=40), nullable=False),
        sa.Column("source_schema_version", sa.String(length=40), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_landing_manifests_batch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "imported_file_id"],
            ["imported_files.tenant_id", "imported_files.id"],
            name="fk_landing_manifests_file_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "batch_id", name="uq_landing_manifests_batch"),
    )
    op.create_table(
        "lineage_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("staging_record_id", sa.Uuid(), nullable=True),
        sa.Column("source_entity", sa.String(length=60), nullable=False),
        sa.Column("source_external_id", sa.String(length=240), nullable=False),
        sa.Column("source_version", sa.String(length=100), nullable=False),
        sa.Column("target_entity", sa.String(length=60), nullable=False),
        sa.Column("target_record_id", sa.String(length=240), nullable=False),
        sa.Column("operation", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_lineage_events_batch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            name="fk_lineage_events_staging_same_tenant",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lineage_events_created_brin",
        "lineage_events",
        ["created_at"],
        unique=False,
        postgresql_using="brin",
    )
    op.create_index(
        "ix_lineage_events_target",
        "lineage_events",
        ["tenant_id", "target_entity", "target_record_id"],
        unique=False,
    )
    op.create_table(
        "processing_errors",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("staging_record_id", sa.Uuid(), nullable=True),
        sa.Column("step_name", sa.String(length=60), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=True),
        sa.Column("field_name", sa.String(length=160), nullable=True),
        sa.Column("error_class", sa.String(length=60), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=24), nullable=False),
        sa.Column("message", sa.String(length=800), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "severity IN ('informational','warning','error','blocking')",
            name="ck_processing_errors_severity",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_processing_errors_batch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            name="fk_processing_errors_staging_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_processing_errors_batch_code",
        "processing_errors",
        ["tenant_id", "batch_id", "error_code"],
        unique=False,
    )
    op.create_table(
        "processing_steps",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("step_name", sa.String(length=60), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "state IN ('created','queued','connecting','extracting','received','validating','mapping','normalizing','loading','completed','completed_with_warnings','failed','cancelled','quarantined','retry_scheduled')",
            name="ck_processing_steps_state",
        ),
        sa.ForeignKeyConstraint(["execution_id"], ["sync_executions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_processing_steps_batch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "batch_id",
            "step_name",
            "attempt_number",
            name="uq_processing_steps_batch_name_attempt",
        ),
    )
    op.create_table(
        "rejected_records",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("staging_record_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("correction_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("corrected_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "status IN ('open','corrected','ignored','reprocessed')",
            name="ck_rejected_records_status",
        ),
        sa.ForeignKeyConstraint(["corrected_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_rejected_records_batch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            name="fk_rejected_records_staging_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "staging_record_id", name="uq_rejected_records_staging"),
    )
    op.create_index(
        "ix_rejected_records_batch_status",
        "rejected_records",
        ["tenant_id", "batch_id", "status"],
        unique=False,
    )
    op.create_table(
        "sync_attempts",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("worker_id", sa.String(length=160), nullable=True),
        sa.Column("error_class", sa.String(length=60), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "state IN ('created','queued','connecting','extracting','received','validating','mapping','normalizing','loading','completed','completed_with_warnings','failed','cancelled','quarantined','retry_scheduled')",
            name="ck_sync_attempts_state",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "execution_id"],
            ["sync_executions.tenant_id", "sync_executions.id"],
            name="fk_sync_attempts_execution_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "execution_id", "attempt_number", name="uq_sync_attempts_execution_number"
        ),
    )
    op.create_table(
        "sync_checkpoints",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("step_name", sa.String(length=60), nullable=False),
        sa.Column("cursor_value", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("records_committed", sa.BigInteger(), nullable=False),
        sa.Column("source_version", sa.String(length=100), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "execution_id"],
            ["sync_executions.tenant_id", "sync_executions.id"],
            name="fk_sync_checkpoints_execution_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "execution_id", "step_name", name="uq_sync_checkpoints_execution_step"
        ),
    )
    op.create_table(
        "canonical_inventory_lots",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("lot_number", sa.String(length=120), nullable=False),
        sa.Column("manufactured_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_canonical_inventory_lots_branch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            name="fk_canonical_inventory_lots_product_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "branch_id",
            "product_id",
            "lot_number",
            name="uq_canonical_inventory_lots_number",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_canonical_inventory_lots_tenant_id"),
    )
    op.create_table(
        "canonical_product_identifiers",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=True),
        sa.Column("identifier_type", sa.String(length=40), nullable=False),
        sa.Column("identifier_value", sa.String(length=180), nullable=False),
        sa.Column("primary", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            name="fk_canonical_product_identifiers_source_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            name="fk_canonical_product_identifiers_product_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "identifier_type",
            "identifier_value",
            name="uq_canonical_product_identifiers_value",
        ),
    )
    op.create_index(
        "ix_canonical_product_identifiers_lookup",
        "canonical_product_identifiers",
        ["tenant_id", "identifier_value"],
        unique=False,
    )
    op.create_table(
        "canonical_product_presentations",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("unit", sa.String(length=24), nullable=False),
        sa.Column("conversion_factor", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("barcode", sa.String(length=40), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "conversion_factor > 0", name="ck_canonical_product_presentations_factor"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            name="fk_canonical_product_presentations_product_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "product_id", "name", name="uq_canonical_product_presentations_name"
        ),
    )
    op.create_table(
        "canonical_product_prices",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("staging_record_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=240), nullable=False),
        sa.Column("source_version", sa.String(length=100), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("reference_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("reference_cost", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("decision_source", sa.String(length=60), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "price >= 0 AND (reference_price IS NULL OR reference_price >= 0) AND (reference_cost IS NULL OR reference_cost >= 0)",
            name="ck_canonical_product_prices_values",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_canonical_product_prices_batch_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_canonical_product_prices_branch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            name="fk_canonical_product_prices_source_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            name="fk_canonical_product_prices_product_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            name="fk_canonical_product_prices_staging_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "external_id",
            "valid_from",
            name="uq_canonical_product_prices_source_external",
        ),
    )
    op.create_index(
        "ix_canonical_product_prices_scope_valid",
        "canonical_product_prices",
        ["tenant_id", "branch_id", "valid_from"],
        unique=False,
    )
    op.create_index(
        "ix_canonical_product_prices_valid_brin",
        "canonical_product_prices",
        ["valid_from"],
        unique=False,
        postgresql_using="brin",
    )
    op.create_table(
        "canonical_promotion_products",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("promotion_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("promotional_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            name="fk_canonical_promotion_products_product_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "promotion_id"],
            ["canonical_promotions.tenant_id", "canonical_promotions.id"],
            name="fk_canonical_promotion_products_promotion_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "promotion_id", "product_id", name="uq_canonical_promotion_products_pair"
        ),
    )
    op.create_table(
        "canonical_purchase_orders",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("staging_record_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=240), nullable=False),
        sa.Column("source_version", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accounting_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merchandise_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("discount_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("bonus_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("freight_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("tax_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("net_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_canonical_purchase_orders_batch_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_canonical_purchase_orders_branch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            name="fk_canonical_purchase_orders_source_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            name="fk_canonical_purchase_orders_staging_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["canonical_suppliers.tenant_id", "canonical_suppliers.id"],
            name="fk_canonical_purchase_orders_supplier_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "external_id",
            name="uq_canonical_purchase_orders_source_external",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_canonical_purchase_orders_tenant_id"),
    )
    op.create_index(
        "ix_canonical_purchase_orders_ordered_brin",
        "canonical_purchase_orders",
        ["ordered_at"],
        unique=False,
        postgresql_using="brin",
    )
    op.create_index(
        "ix_canonical_purchase_orders_scope_date",
        "canonical_purchase_orders",
        ["tenant_id", "company_id", "branch_id", "ordered_at"],
        unique=False,
    )
    op.create_table(
        "canonical_sale_adjustments",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("sale_id", sa.Uuid(), nullable=False),
        sa.Column("sale_occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("adjustment_type", sa.String(length=24), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "adjustment_type IN ('cancellation','return','discount','charge')",
            name="ck_canonical_sale_adjustments_type",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sale_id", "sale_occurred_at"],
            ["canonical_sales.tenant_id", "canonical_sales.id", "canonical_sales.occurred_at"],
            name="fk_canonical_sale_adjustments_sale_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "canonical_sale_items",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("sale_id", sa.Uuid(), nullable=False),
        sa.Column("sale_occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("gross_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("discount_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("tax_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("net_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "quantity <> 0 AND gross_total >= 0 AND discount_total >= 0 AND net_total >= 0",
            name="ck_canonical_sale_items_values",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            name="fk_canonical_sale_items_product_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sale_id", "sale_occurred_at"],
            ["canonical_sales.tenant_id", "canonical_sales.id", "canonical_sales.occurred_at"],
            name="fk_canonical_sale_items_sale_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "sale_id",
            "sale_occurred_at",
            "line_number",
            name="uq_canonical_sale_items_line",
        ),
    )
    op.create_index(
        "ix_canonical_sale_items_product",
        "canonical_sale_items",
        ["tenant_id", "product_id", "sale_occurred_at"],
        unique=False,
    )
    op.create_table(
        "canonical_sale_payments",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("sale_id", sa.Uuid(), nullable=False),
        sa.Column("sale_occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(length=60), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("installments", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint("amount >= 0", name="ck_canonical_sale_payments_amount"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sale_id", "sale_occurred_at"],
            ["canonical_sales.tenant_id", "canonical_sales.id", "canonical_sales.occurred_at"],
            name="fk_canonical_sale_payments_sale_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "canonical_stock_balances",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("staging_record_id", sa.Uuid(), nullable=False),
        sa.Column("source_version", sa.String(length=100), nullable=False),
        sa.Column("on_hand", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("reserved", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("in_transit", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("updated_from_source_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "on_hand >= 0 AND reserved >= 0 AND in_transit >= 0 AND reserved <= on_hand",
            name="ck_canonical_stock_balances_values",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_canonical_stock_balances_batch_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_canonical_stock_balances_branch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            name="fk_canonical_stock_balances_source_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            name="fk_canonical_stock_balances_product_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            name="fk_canonical_stock_balances_staging_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "branch_id", "product_id", name="uq_canonical_stock_balances_product"
        ),
    )
    op.create_index(
        "ix_canonical_stock_balances_scope",
        "canonical_stock_balances",
        ["tenant_id", "company_id", "branch_id"],
        unique=False,
    )
    op.create_table(
        "canonical_stock_snapshots",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("on_hand", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("reserved", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("in_transit", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "on_hand >= 0 AND reserved >= 0 AND in_transit >= 0",
            name="ck_canonical_stock_snapshots_values",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_canonical_stock_snapshots_batch_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_canonical_stock_snapshots_branch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            name="fk_canonical_stock_snapshots_product_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_canonical_stock_snapshots_at_brin",
        "canonical_stock_snapshots",
        ["snapshot_at"],
        unique=False,
        postgresql_using="brin",
    )
    op.create_index(
        "ix_canonical_stock_snapshots_scope_at",
        "canonical_stock_snapshots",
        ["tenant_id", "branch_id", "snapshot_at"],
        unique=False,
    )
    op.create_table(
        "canonical_supplier_identifiers",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("identifier_type", sa.String(length=40), nullable=False),
        sa.Column("identifier_value", sa.String(length=180), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["canonical_suppliers.tenant_id", "canonical_suppliers.id"],
            name="fk_canonical_supplier_identifiers_supplier_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "identifier_type",
            "identifier_value",
            name="uq_canonical_supplier_identifiers_value",
        ),
    )
    op.create_table(
        "canonical_supplier_products",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_product_code", sa.String(length=160), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=False),
        sa.Column("minimum_order", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("purchase_multiple", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("current_cost", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "lead_time_days >= 0 AND minimum_order >= 0 AND purchase_multiple > 0",
            name="ck_canonical_supplier_products_terms",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            name="fk_canonical_supplier_products_product_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["canonical_suppliers.tenant_id", "canonical_suppliers.id"],
            name="fk_canonical_supplier_products_supplier_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_canonical_supplier_products_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "supplier_id", "product_id", name="uq_canonical_supplier_products_pair"
        ),
    )
    op.create_table(
        "canonical_inventory_movements",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("inventory_lot_id", sa.Uuid(), nullable=True),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("staging_record_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=240), nullable=False),
        sa.Column("source_version", sa.String(length=100), nullable=False),
        sa.Column("movement_type", sa.String(length=24), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("balance_after", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accounting_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reference_type", sa.String(length=60), nullable=True),
        sa.Column("reference_id", sa.String(length=240), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "movement_type IN ('receipt','sale','adjustment','transfer_in','transfer_out','loss','damage','return','inventory','reservation','transit')",
            name="ck_canonical_inventory_movements_type",
        ),
        sa.CheckConstraint("quantity <> 0", name="ck_canonical_inventory_movements_quantity"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_canonical_inventory_movements_batch_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_canonical_inventory_movements_branch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            name="fk_canonical_inventory_movements_source_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "inventory_lot_id"],
            ["canonical_inventory_lots.tenant_id", "canonical_inventory_lots.id"],
            name="fk_canonical_inventory_movements_lot_same_tenant",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            name="fk_canonical_inventory_movements_product_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            name="fk_canonical_inventory_movements_staging_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "external_id",
            name="uq_canonical_inventory_movements_source_external",
        ),
    )
    op.create_index(
        "ix_canonical_inventory_movements_at_brin",
        "canonical_inventory_movements",
        ["occurred_at"],
        unique=False,
        postgresql_using="brin",
    )
    op.create_index(
        "ix_canonical_inventory_movements_scope_at",
        "canonical_inventory_movements",
        ["tenant_id", "branch_id", "occurred_at"],
        unique=False,
    )
    op.create_table(
        "canonical_purchase_items",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("discount_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("bonus_quantity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("tax_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("net_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "quantity > 0 AND unit_cost >= 0 AND net_total >= 0",
            name="ck_canonical_purchase_items_values",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            name="fk_canonical_purchase_items_product_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["canonical_purchase_orders.tenant_id", "canonical_purchase_orders.id"],
            name="fk_canonical_purchase_items_order_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "purchase_order_id", "line_number", name="uq_canonical_purchase_items_line"
        ),
    )
    op.create_table(
        "canonical_purchase_receipts",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(length=24), nullable=False),
        sa.Column("document_number", sa.String(length=120), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "document_type IN ('receipt','invoice','return','cancellation')",
            name="ck_canonical_purchase_receipts_type",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["canonical_purchase_orders.tenant_id", "canonical_purchase_orders.id"],
            name="fk_canonical_purchase_receipts_order_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "purchase_order_id",
            "document_number",
            name="uq_canonical_purchase_receipts_document",
        ),
    )
    op.create_table(
        "canonical_supplier_costs",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_product_id", sa.Uuid(), nullable=False),
        sa.Column("cost", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint("cost >= 0", name="ck_canonical_supplier_costs_cost"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            name="fk_canonical_supplier_costs_batch_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_product_id"],
            ["canonical_supplier_products.tenant_id", "canonical_supplier_products.id"],
            name="fk_canonical_supplier_costs_link_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_canonical_supplier_costs_history",
        "canonical_supplier_costs",
        ["tenant_id", "supplier_product_id", "valid_from"],
        unique=False,
    )
    # Keep hot sales data in a bounded partition and retain a safe default for late/future data.
    op.execute(
        "CREATE TABLE canonical_sales_2026_q3 PARTITION OF canonical_sales "
        "FOR VALUES FROM ('2026-07-01 00:00:00+00') TO ('2026-10-01 00:00:00+00')"
    )
    op.execute("CREATE TABLE canonical_sales_default PARTITION OF canonical_sales DEFAULT")

    connector_table = sa.table(
        "connector_definitions",
        sa.column("id", UUID),
        sa.column("connector_key", sa.String()),
        sa.column("name", sa.String()),
        sa.column("version", sa.String()),
        sa.column("schema_version", sa.String()),
        sa.column("capabilities", postgresql.JSONB()),
        sa.column("authentication_types", postgresql.JSONB()),
        sa.column("supported_entities", postgresql.JSONB()),
        sa.column("status", sa.String()),
    )
    op.bulk_insert(
        connector_table,
        [
            {
                "id": _uuid("connector", "deterministic-erp:1.0.0"),
                "connector_key": "deterministic-erp",
                "name": "ERP determinístico de referência",
                "version": "1.0.0",
                "schema_version": "2026-07",
                "capabilities": [
                    "connection_test",
                    "discovery",
                    "full_sync",
                    "incremental_sync",
                    "pagination",
                    "checkpoint",
                    "cooperative_cancel",
                ],
                "authentication_types": ["none"],
                "supported_entities": [
                    "product",
                    "supplier",
                    "sale",
                    "purchase",
                    "stock",
                    "price",
                ],
                "status": "active",
            },
            {
                "id": _uuid("connector", "file-upload:1.0.0"),
                "connector_key": "file-upload",
                "name": "Importação de arquivo",
                "version": "1.0.0",
                "schema_version": "2026-07",
                "capabilities": ["connection_test", "checkpoint"],
                "authentication_types": ["none"],
                "supported_entities": [
                    "product",
                    "supplier",
                    "sale",
                    "purchase",
                    "stock",
                    "price",
                ],
                "status": "active",
            },
        ],
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
                "catalog_version": 2,
            }
            for key, scope, description in INTEGRATION_PERMISSIONS
        ],
    )
    op.execute("ALTER TABLE role_permissions DISABLE TRIGGER role_permissions_protect_system")
    for role_slug, permission_keys in ROLE_PERMISSION_GRANTS.items():
        keys_sql = ",".join(f"'{key}'" for key in permission_keys)
        op.execute(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT role.id, permission.id FROM roles AS role "
            "CROSS JOIN permissions AS permission "
            f"WHERE role.slug = '{role_slug}' AND role.is_system = true "
            f"AND permission.key IN ({keys_sql}) ON CONFLICT DO NOTHING"
        )
    op.execute("ALTER TABLE role_permissions ENABLE TRIGGER role_permissions_protect_system")

    quality_rule_table = sa.table(
        "quality_rules",
        sa.column("id", UUID),
        sa.column("tenant_id", UUID),
        sa.column("rule_key", sa.String()),
        sa.column("rule_type", sa.String()),
        sa.column("entity_type", sa.String()),
        sa.column("severity", sa.String()),
        sa.column("configuration", postgresql.JSONB()),
        sa.column("active", sa.Boolean()),
        sa.column("is_platform_rule", sa.Boolean()),
        sa.column("version", sa.Integer()),
    )
    op.bulk_insert(
        quality_rule_table,
        [
            {
                "id": _uuid("quality-rule", rule_type),
                "tenant_id": None,
                "rule_key": f"platform.{rule_type}",
                "rule_type": rule_type,
                "entity_type": None,
                "severity": severity,
                "configuration": {},
                "active": True,
                "is_platform_rule": True,
                "version": 1,
            }
            for rule_type, severity in QUALITY_RULES
        ],
    )

    for table in TENANT_TABLES:
        _enable_rls(table)
    quality_using = (
        "tenant_id IS NULL "
        "OR tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
        "OR current_setting('app.is_platform_admin', true) = 'true'"
    )
    quality_check = (
        "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
        "OR current_setting('app.is_platform_admin', true) = 'true'"
    )
    _enable_rls("quality_rules", using=quality_using, check=quality_check)
    _enable_rls("canonical_sales_2026_q3")
    _enable_rls("canonical_sales_default")

    op.execute(
        """
        CREATE FUNCTION validate_integration_state_transition() RETURNS trigger AS $$
        BEGIN
          IF OLD.state = NEW.state THEN
            RETURN NEW;
          END IF;
          IF NOT (
            (OLD.state = 'created' AND NEW.state IN ('queued','cancelled','failed')) OR
            (OLD.state = 'queued' AND NEW.state IN
              ('connecting','received','cancelled','retry_scheduled','failed')) OR
            (OLD.state = 'connecting' AND NEW.state IN
              ('extracting','cancelled','retry_scheduled','failed')) OR
            (OLD.state = 'extracting' AND NEW.state IN
              ('received','cancelled','retry_scheduled','failed')) OR
            (OLD.state = 'received' AND NEW.state IN
              ('validating','cancelled','retry_scheduled','failed')) OR
            (OLD.state = 'validating' AND NEW.state IN
              ('mapping','quarantined','cancelled','retry_scheduled','failed')) OR
            (OLD.state = 'mapping' AND NEW.state IN
              ('normalizing','quarantined','cancelled','retry_scheduled','failed')) OR
            (OLD.state = 'normalizing' AND NEW.state IN
              ('loading','quarantined','cancelled','retry_scheduled','failed')) OR
            (OLD.state = 'loading' AND NEW.state IN
              ('completed','completed_with_warnings','quarantined','cancelled',
               'retry_scheduled','failed')) OR
            (OLD.state = 'retry_scheduled' AND NEW.state IN
              ('queued','connecting','received','validating','mapping','normalizing',
               'loading','cancelled','failed')) OR
            (OLD.state = 'quarantined' AND NEW.state IN ('queued','cancelled','failed')) OR
            (OLD.state = 'failed' AND NEW.state IN ('queued','cancelled'))
          ) THEN
            RAISE EXCEPTION 'invalid integration state transition: % -> %', OLD.state, NEW.state;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER import_batches_validate_state BEFORE UPDATE OF state ON import_batches "
        "FOR EACH ROW EXECUTE FUNCTION validate_integration_state_transition()"
    )
    op.execute(
        "CREATE TRIGGER sync_executions_validate_state BEFORE UPDATE OF state ON sync_executions "
        "FOR EACH ROW EXECUTE FUNCTION validate_integration_state_transition()"
    )
    op.execute(
        """
        CREATE FUNCTION protect_immutable_imported_file() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            IF OLD.retention_until > current_date THEN
              RAISE EXCEPTION 'landing object retention period has not expired';
            END IF;
            RETURN OLD;
          END IF;
          IF OLD.immutable AND (
            OLD.object_bucket IS DISTINCT FROM NEW.object_bucket OR
            OLD.object_key IS DISTINCT FROM NEW.object_key OR
            OLD.content_sha256 IS DISTINCT FROM NEW.content_sha256 OR
            OLD.size_bytes IS DISTINCT FROM NEW.size_bytes
          ) THEN
            RAISE EXCEPTION 'immutable landing metadata cannot be changed';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER imported_files_protect_immutable BEFORE UPDATE OR DELETE "
        "ON imported_files FOR EACH ROW EXECUTE FUNCTION protect_immutable_imported_file()"
    )
    op.execute("REVOKE INSERT, UPDATE, DELETE ON connector_definitions FROM PUBLIC")
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.execute("DROP TRIGGER IF EXISTS imported_files_protect_immutable ON imported_files")
    op.execute("DROP FUNCTION IF EXISTS protect_immutable_imported_file()")
    op.execute("DROP TRIGGER IF EXISTS sync_executions_validate_state ON sync_executions")
    op.execute("DROP TRIGGER IF EXISTS import_batches_validate_state ON import_batches")
    op.execute("DROP FUNCTION IF EXISTS validate_integration_state_transition()")
    op.execute("ALTER TABLE role_permissions DISABLE TRIGGER role_permissions_protect_system")
    permission_keys_sql = ",".join(f"'{key}'" for key in _ALL_INTEGRATION_PERMISSION_KEYS)
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id IN "
        f"(SELECT id FROM permissions WHERE key IN ({permission_keys_sql}))"
    )
    op.execute(f"DELETE FROM permissions WHERE key IN ({permission_keys_sql})")
    op.execute("ALTER TABLE role_permissions ENABLE TRIGGER role_permissions_protect_system")
    op.drop_index("ix_canonical_supplier_costs_history", table_name="canonical_supplier_costs")
    op.drop_table("canonical_supplier_costs")
    op.drop_table("canonical_purchase_receipts")
    op.drop_table("canonical_purchase_items")
    op.drop_index(
        "ix_canonical_inventory_movements_scope_at", table_name="canonical_inventory_movements"
    )
    op.drop_index(
        "ix_canonical_inventory_movements_at_brin",
        table_name="canonical_inventory_movements",
        postgresql_using="brin",
    )
    op.drop_table("canonical_inventory_movements")
    op.drop_table("canonical_supplier_products")
    op.drop_table("canonical_supplier_identifiers")
    op.drop_index("ix_canonical_stock_snapshots_scope_at", table_name="canonical_stock_snapshots")
    op.drop_index(
        "ix_canonical_stock_snapshots_at_brin",
        table_name="canonical_stock_snapshots",
        postgresql_using="brin",
    )
    op.drop_table("canonical_stock_snapshots")
    op.drop_index("ix_canonical_stock_balances_scope", table_name="canonical_stock_balances")
    op.drop_table("canonical_stock_balances")
    op.drop_table("canonical_sale_payments")
    op.drop_index("ix_canonical_sale_items_product", table_name="canonical_sale_items")
    op.drop_table("canonical_sale_items")
    op.drop_table("canonical_sale_adjustments")
    op.drop_index("ix_canonical_purchase_orders_scope_date", table_name="canonical_purchase_orders")
    op.drop_index(
        "ix_canonical_purchase_orders_ordered_brin",
        table_name="canonical_purchase_orders",
        postgresql_using="brin",
    )
    op.drop_table("canonical_purchase_orders")
    op.drop_table("canonical_promotion_products")
    op.drop_index(
        "ix_canonical_product_prices_valid_brin",
        table_name="canonical_product_prices",
        postgresql_using="brin",
    )
    op.drop_index("ix_canonical_product_prices_scope_valid", table_name="canonical_product_prices")
    op.drop_table("canonical_product_prices")
    op.drop_table("canonical_product_presentations")
    op.drop_index(
        "ix_canonical_product_identifiers_lookup", table_name="canonical_product_identifiers"
    )
    op.drop_table("canonical_product_identifiers")
    op.drop_table("canonical_inventory_lots")
    op.drop_table("sync_checkpoints")
    op.drop_table("sync_attempts")
    op.drop_index("ix_rejected_records_batch_status", table_name="rejected_records")
    op.drop_table("rejected_records")
    op.drop_table("processing_steps")
    op.drop_index("ix_processing_errors_batch_code", table_name="processing_errors")
    op.drop_table("processing_errors")
    op.drop_index("ix_lineage_events_target", table_name="lineage_events")
    op.drop_index(
        "ix_lineage_events_created_brin", table_name="lineage_events", postgresql_using="brin"
    )
    op.drop_table("lineage_events")
    op.drop_table("landing_manifests")
    op.drop_index("ix_integration_dead_letters_status", table_name="integration_dead_letters")
    op.drop_table("integration_dead_letters")
    op.drop_index("ix_canonical_suppliers_scope_name", table_name="canonical_suppliers")
    op.drop_table("canonical_suppliers")
    op.drop_index("ix_canonical_sales_scope_occurred", table_name="canonical_sales")
    op.drop_index(
        "ix_canonical_sales_occurred_brin", table_name="canonical_sales", postgresql_using="brin"
    )
    op.drop_table("canonical_sales")
    op.drop_index("ix_canonical_products_scope_name", table_name="canonical_products")
    op.drop_table("canonical_products")
    op.drop_index("ix_sync_executions_source_created", table_name="sync_executions")
    op.drop_table("sync_executions")
    op.drop_index(
        "ix_staging_records_occurred_brin", table_name="staging_records", postgresql_using="brin"
    )
    op.drop_index("ix_staging_records_batch_status", table_name="staging_records")
    op.drop_table("staging_records")
    op.drop_index("ix_quality_results_batch_entity", table_name="quality_results")
    op.drop_table("quality_results")
    op.drop_table("processing_statistics")
    op.drop_index("ix_imported_files_retention", table_name="imported_files")
    op.drop_table("imported_files")
    op.drop_table("canonical_promotions")
    op.drop_index("ix_import_batches_scope_created", table_name="import_batches")
    op.drop_index(
        "ix_import_batches_active",
        table_name="import_batches",
        postgresql_where=sa.text(
            "state NOT IN ('completed','completed_with_warnings','cancelled')"
        ),
    )
    op.drop_table("import_batches")
    op.drop_table("field_mappings")
    op.drop_table("mapping_versions")
    op.drop_table("webhook_receipts")
    op.drop_table("sync_cursors")
    op.drop_table("mapping_profiles")
    op.drop_table("integration_inbox_messages")
    op.drop_index("ix_data_sources_scope_status", table_name="data_sources")
    op.drop_table("data_sources")
    op.drop_index("ix_connector_instances_scope", table_name="connector_instances")
    op.drop_table("connector_instances")
    op.drop_index("ix_credential_references_scope", table_name="credential_references")
    op.drop_table("credential_references")
    op.drop_index(
        "uq_quality_rules_tenant_key",
        table_name="quality_rules",
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_quality_rules_platform_key",
        table_name="quality_rules",
        postgresql_where=sa.text("tenant_id IS NULL"),
    )
    op.drop_table("quality_rules")
    op.drop_index(
        "ix_processing_state_transitions_resource", table_name="processing_state_transitions"
    )
    op.drop_table("processing_state_transitions")
    op.drop_index("ix_processing_leases_expiry", table_name="processing_leases")
    op.drop_table("processing_leases")
    op.drop_index(
        "ix_integration_outbox_pending",
        table_name="integration_outbox_events",
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.drop_table("integration_outbox_events")
    op.drop_table("canonical_manufacturers")
    op.drop_index("ix_canonical_categories_parent", table_name="canonical_categories")
    op.drop_table("canonical_categories")
    op.drop_table("canonical_brands")
    op.drop_table("connector_definitions")
    # ### end Alembic commands ###
