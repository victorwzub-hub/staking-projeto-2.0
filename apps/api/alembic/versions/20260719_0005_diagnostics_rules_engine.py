"""Materialize diagnostics catalogs, operations, permissions and tenant RLS.

Revision ID: 20260719_0005
Revises: 20260718_0004
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from pharma_api.infrastructure.db.migration_data.diagnostic_action_catalog_v1 import (
    ACTION_COUNT,
    CATALOG_HASH,
    CATALOG_VERSION,
    SNAPSHOT_ID,
    SOURCE_REVISION,
    iter_entry_rows,
)

revision: str = "20260719_0005"
down_revision: str | None = "20260718_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
SEED_EFFECTIVE_AT = datetime(2026, 7, 19, tzinfo=UTC)

DIAGNOSTIC_PERMISSIONS: tuple[tuple[str, str, str], ...] = (
    (
        "diagnostics.view",
        "company",
        "Visualizar diagnósticos, evidências, hipóteses e incidentes",
    ),
    (
        "diagnostics.evaluate",
        "company",
        "Solicitar avaliações diagnósticas determinísticas",
    ),
    (
        "diagnostics.rules.manage",
        "tenant",
        "Administrar regras diagnósticas e configurações seguras",
    ),
    (
        "diagnostics.suppress",
        "company",
        "Gerenciar supressões e cooldowns diagnósticos",
    ),
    (
        "diagnostics.incidents.manage",
        "company",
        "Reconhecer e resolver incidentes diagnósticos",
    ),
)
_ALL_DIAGNOSTIC_PERMISSION_KEYS = tuple(key for key, _, _ in DIAGNOSTIC_PERMISSIONS)
ROLE_PERMISSION_GRANTS: dict[str, tuple[str, ...]] = {
    "tenant_owner": _ALL_DIAGNOSTIC_PERMISSION_KEYS,
    "tenant_admin": _ALL_DIAGNOSTIC_PERMISSION_KEYS,
    "company_admin": _ALL_DIAGNOSTIC_PERMISSION_KEYS,
    "branch_manager": (
        "diagnostics.view",
        "diagnostics.evaluate",
        "diagnostics.suppress",
        "diagnostics.incidents.manage",
    ),
    "analyst": ("diagnostics.view", "diagnostics.evaluate"),
    "consultant": ("diagnostics.view",),
    "accountant": ("diagnostics.view",),
    "viewer": ("diagnostics.view",),
}

TENANT_TABLES: tuple[str, ...] = (
    "diagnostic_rule_configurations",
    "diagnostic_evaluation_runs",
    "diagnostic_findings",
    "diagnostic_evidences",
    "diagnostic_hypotheses",
    "diagnostic_hypothesis_evidences",
    "diagnostic_action_recommendations",
    "diagnostic_suppressions",
    "diagnostic_incidents",
    "diagnostic_incident_memberships",
)
GLOBAL_CATALOG_TABLES: tuple[str, ...] = (
    "diagnostic_action_catalog_snapshots",
    "diagnostic_action_catalog_entries",
)


def _uuid(kind: str, value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"pharma-intelligence:{kind}:{value}"))


def _current_tenant_expression(column: str = "tenant_id") -> str:
    return (
        f"{column} = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
        "OR current_setting('app.is_platform_admin', true) = 'true'"
    )


def _enable_tenant_rls(table: str) -> None:
    expression = _current_tenant_expression()
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY "{table}_tenant_policy" ON "{table}" '
        f"USING ({expression}) WITH CHECK ({expression})"
    )


def _enable_rule_definition_rls() -> None:
    table = "diagnostic_rule_definitions"
    own_tenant = _current_tenant_expression()
    admin = "current_setting('app.is_platform_admin', true) = 'true'"
    readable = f"tenant_id IS NULL OR tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid OR {admin}"
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY "{table}_select_policy" ON "{table}" FOR SELECT USING ({readable})')
    op.execute(
        f'CREATE POLICY "{table}_insert_policy" ON "{table}" FOR INSERT WITH CHECK ({own_tenant})'
    )
    op.execute(
        f'CREATE POLICY "{table}_update_policy" ON "{table}" FOR UPDATE USING ({own_tenant}) WITH CHECK ({own_tenant})'
    )
    op.execute(
        f'CREATE POLICY "{table}_delete_policy" ON "{table}" FOR DELETE USING ({own_tenant})'
    )


def _enable_rule_version_rls() -> None:
    table = "diagnostic_rule_versions"
    admin = "current_setting('app.is_platform_admin', true) = 'true'"
    visible_definition = (
        "EXISTS (SELECT 1 FROM diagnostic_rule_definitions definition "
        "WHERE definition.id = diagnostic_rule_versions.rule_definition_id AND "
        "(definition.tenant_id IS NULL OR definition.tenant_id = "
        "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid))"
    )
    writable_definition = (
        "EXISTS (SELECT 1 FROM diagnostic_rule_definitions definition "
        "WHERE definition.id = diagnostic_rule_versions.rule_definition_id AND "
        "definition.tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)"
    )
    readable = f"({visible_definition}) OR {admin}"
    writable = f"({writable_definition}) OR {admin}"
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY "{table}_select_policy" ON "{table}" FOR SELECT USING ({readable})')
    op.execute(
        f'CREATE POLICY "{table}_insert_policy" ON "{table}" FOR INSERT WITH CHECK ({writable})'
    )
    op.execute(
        f'CREATE POLICY "{table}_update_policy" ON "{table}" FOR UPDATE USING ({writable}) WITH CHECK ({writable})'
    )
    op.execute(f'CREATE POLICY "{table}_delete_policy" ON "{table}" FOR DELETE USING ({writable})')


def _enable_global_catalog_rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY "{table}_select_policy" ON "{table}" FOR SELECT USING (true)')
    op.execute(f'REVOKE INSERT, UPDATE, DELETE ON "{table}" FROM PUBLIC')


def _seed_permissions() -> None:
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
                "catalog_version": 4,
            }
            for key, scope, description in DIAGNOSTIC_PERMISSIONS
        ],
    )
    op.execute("ALTER TABLE role_permissions DISABLE TRIGGER role_permissions_protect_system")
    for role_slug, keys in ROLE_PERMISSION_GRANTS.items():
        keys_sql = ",".join(f"'{key}'" for key in keys)
        op.execute(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT role.id, permission.id FROM roles AS role CROSS JOIN permissions AS permission "
            f"WHERE role.slug = '{role_slug}' AND role.is_system = true "
            f"AND permission.key IN ({keys_sql}) ON CONFLICT DO NOTHING"
        )
    op.execute("ALTER TABLE role_permissions ENABLE TRIGGER role_permissions_protect_system")


def _seed_action_catalog() -> None:
    bind = op.get_bind()
    snapshot_table = sa.table(
        "diagnostic_action_catalog_snapshots",
        sa.column("id", UUID),
        sa.column("catalog_version", sa.Integer()),
        sa.column("catalog_hash", sa.String()),
        sa.column("status", sa.String()),
        sa.column("is_current", sa.Boolean()),
        sa.column("effective_from", sa.DateTime(timezone=True)),
        sa.column("effective_to", sa.DateTime(timezone=True)),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("source_revision", sa.String()),
    )
    entry_table = sa.table(
        "diagnostic_action_catalog_entries",
        sa.column("id", UUID),
        sa.column("catalog_snapshot_id", UUID),
        sa.column("action_code", sa.String()),
        sa.column("action_version", sa.Integer()),
        sa.column("title", sa.String()),
        sa.column("domain", sa.String()),
        sa.column("default_priority", sa.Integer()),
        sa.column("status", sa.String()),
        sa.column("effective_from", sa.DateTime(timezone=True)),
        sa.column("effective_to", sa.DateTime(timezone=True)),
        sa.column("definition_snapshot", JSONB),
        sa.column("definition_hash", sa.String()),
        sa.column("execution_mode", sa.String()),
        sa.column("requires_human_review", sa.Boolean()),
    )
    snapshot_insert = postgresql.insert(snapshot_table).values(
        id=SNAPSHOT_ID,
        catalog_version=CATALOG_VERSION,
        catalog_hash=CATALOG_HASH,
        status="published",
        is_current=False,
        effective_from=SEED_EFFECTIVE_AT,
        effective_to=None,
        published_at=SEED_EFFECTIVE_AT,
        source_revision=SOURCE_REVISION,
    )
    bind.execute(snapshot_insert.on_conflict_do_nothing(index_elements=["catalog_version"]))
    snapshot = bind.execute(
        sa.select(
            snapshot_table.c.id,
            snapshot_table.c.catalog_hash,
            snapshot_table.c.source_revision,
        ).where(snapshot_table.c.catalog_version == CATALOG_VERSION)
    ).one()
    if (snapshot.id, snapshot.catalog_hash, snapshot.source_revision) != (
        SNAPSHOT_ID,
        CATALOG_HASH,
        SOURCE_REVISION,
    ):
        raise RuntimeError("diagnostic action catalog snapshot conflicts with frozen seed")

    expected_rows = []
    for row in iter_entry_rows():
        expected = {
            **row,
            "effective_from": SEED_EFFECTIVE_AT,
            "effective_to": None,
        }
        expected_rows.append(expected)
        statement = postgresql.insert(entry_table).values(**expected)
        bind.execute(
            statement.on_conflict_do_nothing(
                constraint="uq_diagnostic_action_catalog_entries_snapshot_code"
            )
        )

    stored_rows = bind.execute(
        sa.select(
            entry_table.c.action_code,
            entry_table.c.action_version,
            entry_table.c.definition_hash,
        ).where(entry_table.c.catalog_snapshot_id == SNAPSHOT_ID)
    ).all()
    stored = {row.action_code: (row.action_version, row.definition_hash) for row in stored_rows}
    expected = {
        str(row["action_code"]): (int(row["action_version"]), str(row["definition_hash"]))
        for row in expected_rows
    }
    if len(stored_rows) != ACTION_COUNT or stored != expected:
        raise RuntimeError("diagnostic action catalog entries conflict with frozen seed")

    bind.execute(
        snapshot_table.update()
        .where(snapshot_table.c.catalog_version != CATALOG_VERSION)
        .values(is_current=False)
    )
    bind.execute(
        snapshot_table.update()
        .where(snapshot_table.c.catalog_version == CATALOG_VERSION)
        .values(is_current=True)
    )


def upgrade() -> None:
    op.create_table(
        "diagnostic_action_catalog_snapshots",
        sa.Column("catalog_version", sa.Integer(), nullable=False),
        sa.Column("catalog_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_revision", sa.String(length=120), nullable=False),
        sa.Column("id", UUID, nullable=False),
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
            "catalog_hash ~ '^[0-9a-f]{64}$'", name="ck_diagnostic_action_catalog_snapshots_hash"
        ),
        sa.CheckConstraint(
            "is_current = false OR status = 'published'",
            name="ck_diagnostic_action_catalog_snapshots_current",
        ),
        sa.CheckConstraint(
            "status <> 'published' OR (published_at IS NOT NULL AND effective_from IS NOT NULL)",
            name="ck_diagnostic_action_catalog_snapshots_publication",
        ),
        sa.CheckConstraint(
            "status IN ('draft','published','retired')",
            name="ck_diagnostic_action_catalog_snapshots_status",
        ),
        sa.CheckConstraint(
            "catalog_version >= 1", name="ck_diagnostic_action_catalog_snapshots_version"
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR (effective_from IS NOT NULL AND effective_to > effective_from)",
            name="ck_diagnostic_action_catalog_snapshots_period",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_hash", name="uq_diagnostic_action_catalog_snapshots_hash"),
        sa.UniqueConstraint(
            "catalog_version", name="uq_diagnostic_action_catalog_snapshots_version"
        ),
    )
    op.create_index(
        "ix_diagnostic_action_catalog_snapshots_status",
        "diagnostic_action_catalog_snapshots",
        ["status", "effective_from"],
        unique=False,
    )
    op.create_index(
        "uq_diagnostic_action_catalog_snapshots_current",
        "diagnostic_action_catalog_snapshots",
        ["is_current"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )
    op.create_table(
        "diagnostic_action_catalog_entries",
        sa.Column("catalog_snapshot_id", UUID, nullable=False),
        sa.Column("action_code", sa.String(length=100), nullable=False),
        sa.Column("action_version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("default_priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("definition_snapshot", JSONB, nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("execution_mode", sa.String(length=32), nullable=False),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False),
        sa.Column("id", UUID, nullable=False),
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
            "COALESCE(definition_snapshot ->> 'allows_automatic_financial_execution', '') = 'false'",
            name="ck_diagnostic_action_catalog_entries_no_financial_execution",
        ),
        sa.CheckConstraint(
            "COALESCE(definition_snapshot ->> 'execution_mode', '') = 'human_review_required'",
            name="ck_diagnostic_action_catalog_entries_snapshot_execution_mode",
        ),
        sa.CheckConstraint(
            "action_code ~ '^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$'",
            name="ck_diagnostic_action_catalog_entries_code",
        ),
        sa.CheckConstraint(
            "definition_hash ~ '^[0-9a-f]{64}$'",
            name="ck_diagnostic_action_catalog_entries_definition_hash",
        ),
        sa.CheckConstraint(
            "domain IN ('inventory','sales','margin','purchases','suppliers','operations')",
            name="ck_diagnostic_action_catalog_entries_domain",
        ),
        sa.CheckConstraint(
            "execution_mode = 'human_review_required'",
            name="ck_diagnostic_action_catalog_entries_execution_mode",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(definition_snapshot) = 'object'",
            name="ck_diagnostic_action_catalog_entries_snapshot",
        ),
        sa.CheckConstraint(
            "status IN ('active','deprecated')", name="ck_diagnostic_action_catalog_entries_status"
        ),
        sa.CheckConstraint(
            "action_version >= 1", name="ck_diagnostic_action_catalog_entries_version"
        ),
        sa.CheckConstraint(
            "default_priority IN (1,2,3,4)", name="ck_diagnostic_action_catalog_entries_priority"
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_diagnostic_action_catalog_entries_period",
        ),
        sa.CheckConstraint(
            "requires_human_review = true", name="ck_diagnostic_action_catalog_entries_human_review"
        ),
        sa.ForeignKeyConstraint(
            ["catalog_snapshot_id"], ["diagnostic_action_catalog_snapshots.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "catalog_snapshot_id",
            "action_code",
            name="uq_diagnostic_action_catalog_entries_snapshot_code",
        ),
    )
    op.create_index(
        "ix_diagnostic_action_catalog_entries_catalog",
        "diagnostic_action_catalog_entries",
        ["catalog_snapshot_id", "domain", "status", "default_priority"],
        unique=False,
    )
    op.create_index(
        "ix_diagnostic_action_catalog_entries_history",
        "diagnostic_action_catalog_entries",
        ["action_code", "action_version"],
        unique=False,
    )
    op.create_table(
        "diagnostic_rule_definitions",
        sa.Column("tenant_id", UUID, nullable=True),
        sa.Column("code", sa.String(length=140), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("ownership_type", sa.String(length=16), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=24), nullable=False),
        sa.Column("current_published_version_number", sa.Integer(), nullable=True),
        sa.Column("enabled_by_default", sa.Boolean(), nullable=False),
        sa.Column("id", UUID, nullable=False),
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
            "(ownership_type = 'system' AND tenant_id IS NULL) OR (ownership_type = 'tenant' AND tenant_id IS NOT NULL)",
            name="ck_diagnostic_rule_definitions_ownership",
        ),
        sa.CheckConstraint(
            "code ~ '^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$'",
            name="ck_diagnostic_rule_definitions_code",
        ),
        sa.CheckConstraint(
            "domain IN ('inventory','sales','margin','purchases','suppliers','operations')",
            name="ck_diagnostic_rule_definitions_domain",
        ),
        sa.CheckConstraint(
            "lifecycle_status IN ('draft','active','deprecated','archived')",
            name="ck_diagnostic_rule_definitions_lifecycle_status",
        ),
        sa.CheckConstraint(
            "ownership_type IN ('system','tenant')",
            name="ck_diagnostic_rule_definitions_ownership_type",
        ),
        sa.CheckConstraint(
            "current_published_version_number IS NULL OR current_published_version_number >= 1",
            name="ck_diagnostic_rule_definitions_current_version",
        ),
        sa.ForeignKeyConstraint(
            ["id", "current_published_version_number"],
            [
                "diagnostic_rule_versions.rule_definition_id",
                "diagnostic_rule_versions.version_number",
            ],
            name="fk_diagnostic_rule_definitions_current_version",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "ownership_type", name="uq_diagnostic_rule_definitions_id_ownership"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "ownership_type",
            name="uq_diagnostic_rule_definitions_tenant_id_ownership",
        ),
    )
    op.create_index(
        "ix_diagnostic_rule_definitions_catalog",
        "diagnostic_rule_definitions",
        ["domain", "lifecycle_status", "code"],
        unique=False,
    )
    op.create_index(
        "uq_diagnostic_rule_definitions_system_code",
        "diagnostic_rule_definitions",
        ["code"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )
    op.create_index(
        "uq_diagnostic_rule_definitions_tenant_code",
        "diagnostic_rule_definitions",
        ["tenant_id", "code"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.create_table(
        "diagnostic_rule_versions",
        sa.Column("rule_definition_id", UUID, nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("condition_document", JSONB, nullable=False),
        sa.Column("condition_hash", sa.String(length=64), nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("kpi_codes", JSONB, nullable=False),
        sa.Column("action_codes", JSONB, nullable=False),
        sa.Column("controls", JSONB, nullable=False),
        sa.Column("evidence_metadata", JSONB, nullable=False),
        sa.Column("hypothesis_metadata", JSONB, nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publication_source", sa.String(length=24), nullable=False),
        sa.Column("published_by_user_id", UUID, nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_revision", sa.String(length=120), nullable=True),
        sa.Column("id", UUID, nullable=False),
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
            "condition_hash ~ '^[0-9a-f]{64}$'", name="ck_diagnostic_rule_versions_condition_hash"
        ),
        sa.CheckConstraint(
            "definition_hash ~ '^[0-9a-f]{64}$'", name="ck_diagnostic_rule_versions_definition_hash"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(action_codes) = 'array'", name="ck_diagnostic_rule_versions_action_codes"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(condition_document) = 'object'",
            name="ck_diagnostic_rule_versions_condition_document",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(controls) = 'object'", name="ck_diagnostic_rule_versions_controls"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence_metadata) = 'object'",
            name="ck_diagnostic_rule_versions_evidence_metadata",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(hypothesis_metadata) = 'object'",
            name="ck_diagnostic_rule_versions_hypothesis_metadata",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(kpi_codes) = 'array'", name="ck_diagnostic_rule_versions_kpi_codes"
        ),
        sa.CheckConstraint(
            "publication_source IN ('system','user','migration')",
            name="ck_diagnostic_rule_versions_publication_source",
        ),
        sa.CheckConstraint(
            "status <> 'published' OR (published_at IS NOT NULL AND effective_from IS NOT NULL)",
            name="ck_diagnostic_rule_versions_publication",
        ),
        sa.CheckConstraint(
            "status IN ('draft','published','retired')", name="ck_diagnostic_rule_versions_status"
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR (effective_from IS NOT NULL AND effective_to > effective_from)",
            name="ck_diagnostic_rule_versions_period",
        ),
        sa.CheckConstraint(
            "version_number >= 1", name="ck_diagnostic_rule_versions_version_number"
        ),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["rule_definition_id"], ["diagnostic_rule_definitions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rule_definition_id",
            "version_number",
            name="uq_diagnostic_rule_versions_definition_version",
        ),
    )
    op.create_index(
        "ix_diagnostic_rule_versions_catalog",
        "diagnostic_rule_versions",
        ["rule_definition_id", "status", "version_number"],
        unique=False,
    )
    op.create_index(
        "ix_diagnostic_rule_versions_effective",
        "diagnostic_rule_versions",
        ["status", "effective_from", "effective_to"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_diagnostic_rule_definitions_current_version",
        "diagnostic_rule_definitions",
        "diagnostic_rule_versions",
        ["id", "current_published_version_number"],
        ["rule_definition_id", "version_number"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "diagnostic_evaluation_runs",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("company_id", UUID, nullable=True),
        sa.Column("branch_id", UUID, nullable=True),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("trigger_type", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("engine_version", sa.String(length=40), nullable=False),
        sa.Column("analytics_data_version", sa.BigInteger(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("requested_by_user_id", UUID, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("rules_evaluated", sa.Integer(), nullable=False),
        sa.Column("rules_skipped", sa.Integer(), nullable=False),
        sa.Column("rule_failures", sa.Integer(), nullable=False),
        sa.Column("diagnostics_generated", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.String(length=32), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("id", UUID, nullable=False),
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
            "(scope_type = 'tenant' AND company_id IS NULL AND branch_id IS NULL) OR (scope_type = 'company' AND company_id IS NOT NULL AND branch_id IS NULL) OR (scope_type = 'branch' AND company_id IS NOT NULL AND branch_id IS NOT NULL)",
            name="ck_diagnostic_evaluation_runs_scope",
        ),
        sa.CheckConstraint(
            "(status = 'failed' AND error_type IS NOT NULL) OR (status <> 'failed' AND error_type IS NULL)",
            name="ck_diagnostic_evaluation_runs_error_state",
        ),
        sa.CheckConstraint(
            "error_type IS NULL OR error_type IN ('validation','analytics_unavailable','rule_failure','internal')",
            name="ck_diagnostic_evaluation_runs_error_type",
        ),
        sa.CheckConstraint(
            "scope_type IN ('tenant','company','branch')",
            name="ck_diagnostic_evaluation_runs_scope_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','completed_with_warnings','failed','cancelled')",
            name="ck_diagnostic_evaluation_runs_status",
        ),
        sa.CheckConstraint(
            "trigger_type IN ('scheduled','manual','data_refresh','replay')",
            name="ck_diagnostic_evaluation_runs_trigger_type",
        ),
        sa.CheckConstraint(
            "analytics_data_version >= 0", name="ck_diagnostic_evaluation_runs_data_version"
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR (started_at IS NOT NULL AND completed_at >= started_at)",
            name="ck_diagnostic_evaluation_runs_period",
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="ck_diagnostic_evaluation_runs_duration"
        ),
        sa.CheckConstraint(
            "rules_evaluated >= 0 AND rules_skipped >= 0 AND rule_failures >= 0 AND diagnostics_generated >= 0",
            name="ck_diagnostic_evaluation_runs_counters",
        ),
        sa.CheckConstraint(
            "window_end >= window_start", name="ck_diagnostic_evaluation_runs_window"
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_diagnostic_evaluation_runs_branch_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            name="fk_diagnostic_evaluation_runs_company_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "id", "branch_id", name="uq_diagnostic_evaluation_runs_tenant_branch"
        ),
        sa.UniqueConstraint(
            "tenant_id", "id", "company_id", name="uq_diagnostic_evaluation_runs_tenant_company"
        ),
        sa.UniqueConstraint(
            "tenant_id", "id", "scope_type", name="uq_diagnostic_evaluation_runs_tenant_scope"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_diagnostic_evaluation_runs_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_diagnostic_evaluation_runs_idempotency"
        ),
    )
    op.create_index(
        "ix_diagnostic_evaluation_runs_scope_created",
        "diagnostic_evaluation_runs",
        ["tenant_id", "company_id", "branch_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_diagnostic_evaluation_runs_status",
        "diagnostic_evaluation_runs",
        ["tenant_id", "status", "created_at"],
        unique=False,
    )
    op.create_table(
        "diagnostic_rule_configurations",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("company_id", UUID, nullable=True),
        sa.Column("branch_id", UUID, nullable=True),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("rule_definition_id", UUID, nullable=False),
        sa.Column("rule_ownership_type", sa.String(length=16), nullable=False),
        sa.Column("rule_tenant_id", UUID, nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("version_policy", sa.String(length=24), nullable=False),
        sa.Column("selected_version_number", sa.Integer(), nullable=True),
        sa.Column("cooldown_hours", sa.Integer(), nullable=True),
        sa.Column("minimum_severity", sa.String(length=16), nullable=False),
        sa.Column("active_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", UUID, nullable=False),
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
            "(rule_ownership_type = 'system' AND rule_tenant_id IS NULL) OR (rule_ownership_type = 'tenant' AND rule_tenant_id = tenant_id)",
            name="ck_diagnostic_rule_configurations_rule_ownership",
        ),
        sa.CheckConstraint(
            "(scope_type = 'tenant' AND company_id IS NULL AND branch_id IS NULL) OR (scope_type = 'company' AND company_id IS NOT NULL AND branch_id IS NULL) OR (scope_type = 'branch' AND company_id IS NOT NULL AND branch_id IS NOT NULL)",
            name="ck_diagnostic_rule_configurations_scope",
        ),
        sa.CheckConstraint(
            "(version_policy = 'follow_published' AND selected_version_number IS NULL) OR (version_policy = 'pinned' AND selected_version_number IS NOT NULL)",
            name="ck_diagnostic_rule_configurations_version_selection",
        ),
        sa.CheckConstraint(
            "minimum_severity IN ('info','low','medium','high','critical')",
            name="ck_diagnostic_rule_configurations_minimum_severity",
        ),
        sa.CheckConstraint(
            "rule_ownership_type IN ('system','tenant')",
            name="ck_diagnostic_rule_configurations_rule_ownership_type",
        ),
        sa.CheckConstraint(
            "scope_type IN ('tenant','company','branch')",
            name="ck_diagnostic_rule_configurations_scope_type",
        ),
        sa.CheckConstraint(
            "version_policy IN ('follow_published','pinned')",
            name="ck_diagnostic_rule_configurations_version_policy",
        ),
        sa.CheckConstraint(
            "active_to IS NULL OR (active_from IS NOT NULL AND active_to > active_from)",
            name="ck_diagnostic_rule_configurations_period",
        ),
        sa.CheckConstraint(
            "cooldown_hours IS NULL OR cooldown_hours BETWEEN 1 AND 720",
            name="ck_diagnostic_rule_configurations_cooldown",
        ),
        sa.CheckConstraint(
            "selected_version_number IS NULL OR selected_version_number >= 1",
            name="ck_diagnostic_rule_configurations_selected_version",
        ),
        sa.ForeignKeyConstraint(
            ["rule_definition_id", "rule_ownership_type"],
            ["diagnostic_rule_definitions.id", "diagnostic_rule_definitions.ownership_type"],
            name="fk_diagnostic_rule_configurations_rule_ownership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rule_definition_id", "selected_version_number"],
            [
                "diagnostic_rule_versions.rule_definition_id",
                "diagnostic_rule_versions.version_number",
            ],
            name="fk_diagnostic_rule_configurations_selected_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rule_tenant_id", "rule_definition_id", "rule_ownership_type"],
            [
                "diagnostic_rule_definitions.tenant_id",
                "diagnostic_rule_definitions.id",
                "diagnostic_rule_definitions.ownership_type",
            ],
            name="fk_diagnostic_rule_configurations_tenant_rule",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_diagnostic_rule_configurations_branch_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            name="fk_diagnostic_rule_configurations_company_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_diagnostic_rule_configurations_tenant_id"),
    )
    op.create_index(
        "ix_diagnostic_rule_configurations_lookup",
        "diagnostic_rule_configurations",
        ["tenant_id", "company_id", "branch_id", "enabled"],
        unique=False,
    )
    op.create_index(
        "uq_diagnostic_rule_configurations_scope",
        "diagnostic_rule_configurations",
        ["tenant_id", "rule_definition_id", "company_id", "branch_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    op.create_table(
        "diagnostic_findings",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("company_id", UUID, nullable=True),
        sa.Column("branch_id", UUID, nullable=True),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("evaluation_run_id", UUID, nullable=False),
        sa.Column("rule_definition_id", UUID, nullable=False),
        sa.Column("rule_version_number", sa.Integer(), nullable=False),
        sa.Column("rule_ownership_type", sa.String(length=16), nullable=False),
        sa.Column("rule_tenant_id", UUID, nullable=True),
        sa.Column("diagnostic_code", sa.String(length=140), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("confidence_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("affected_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("affected_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("primary_kpi_code", sa.String(length=140), nullable=False),
        sa.Column("observed_value", sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column("reference_value", sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column("value_unit", sa.String(length=40), nullable=True),
        sa.Column("analytics_data_version", sa.BigInteger(), nullable=False),
        sa.Column("formula_version", sa.Integer(), nullable=False),
        sa.Column("context_snapshot", JSONB, nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", UUID, nullable=False),
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
            "(rule_ownership_type = 'system' AND rule_tenant_id IS NULL) OR (rule_ownership_type = 'tenant' AND rule_tenant_id = tenant_id)",
            name="ck_diagnostic_findings_rule_ownership",
        ),
        sa.CheckConstraint(
            "(scope_type = 'tenant' AND company_id IS NULL AND branch_id IS NULL) OR (scope_type = 'company' AND company_id IS NOT NULL AND branch_id IS NULL) OR (scope_type = 'branch' AND company_id IS NOT NULL AND branch_id IS NOT NULL)",
            name="ck_diagnostic_findings_scope",
        ),
        sa.CheckConstraint(
            "(status <> 'acknowledged' OR acknowledged_at IS NOT NULL) AND (status <> 'resolved' OR resolved_at IS NOT NULL) AND (status <> 'closed' OR closed_at IS NOT NULL)",
            name="ck_diagnostic_findings_lifecycle",
        ),
        sa.CheckConstraint(
            "diagnostic_code ~ '^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$'",
            name="ck_diagnostic_findings_code",
        ),
        sa.CheckConstraint(
            "domain IN ('inventory','sales','margin','purchases','suppliers','operations')",
            name="ck_diagnostic_findings_domain",
        ),
        sa.CheckConstraint(
            "fingerprint ~ '^[0-9a-f]{64}$'", name="ck_diagnostic_findings_fingerprint"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(context_snapshot) = 'object'",
            name="ck_diagnostic_findings_context_snapshot",
        ),
        sa.CheckConstraint(
            "rule_ownership_type IN ('system','tenant')",
            name="ck_diagnostic_findings_rule_ownership_type",
        ),
        sa.CheckConstraint(
            "scope_type IN ('tenant','company','branch')", name="ck_diagnostic_findings_scope_type"
        ),
        sa.CheckConstraint(
            "severity IN ('info','low','medium','high','critical')",
            name="ck_diagnostic_findings_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open','acknowledged','resolved','closed')",
            name="ck_diagnostic_findings_status",
        ),
        sa.CheckConstraint(
            "affected_to >= affected_from", name="ck_diagnostic_findings_affected_period"
        ),
        sa.CheckConstraint(
            "analytics_data_version >= 0 AND formula_version >= 1 AND rule_version_number >= 1",
            name="ck_diagnostic_findings_versions",
        ),
        sa.CheckConstraint(
            "confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1",
            name="ck_diagnostic_findings_confidence",
        ),
        sa.CheckConstraint(
            "last_observed_at >= first_observed_at",
            name="ck_diagnostic_findings_observation_period",
        ),
        sa.CheckConstraint("occurrence_count >= 1", name="ck_diagnostic_findings_occurrence_count"),
        sa.CheckConstraint("priority IN (1,2,3,4)", name="ck_diagnostic_findings_priority"),
        sa.ForeignKeyConstraint(
            ["rule_definition_id", "rule_ownership_type"],
            ["diagnostic_rule_definitions.id", "diagnostic_rule_definitions.ownership_type"],
            name="fk_diagnostic_findings_rule_ownership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rule_definition_id", "rule_version_number"],
            [
                "diagnostic_rule_versions.rule_definition_id",
                "diagnostic_rule_versions.version_number",
            ],
            name="fk_diagnostic_findings_rule_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rule_tenant_id", "rule_definition_id", "rule_ownership_type"],
            [
                "diagnostic_rule_definitions.tenant_id",
                "diagnostic_rule_definitions.id",
                "diagnostic_rule_definitions.ownership_type",
            ],
            name="fk_diagnostic_findings_tenant_rule",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_diagnostic_findings_branch_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            name="fk_diagnostic_findings_company_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "evaluation_run_id", "branch_id"],
            [
                "diagnostic_evaluation_runs.tenant_id",
                "diagnostic_evaluation_runs.id",
                "diagnostic_evaluation_runs.branch_id",
            ],
            name="fk_diagnostic_findings_run_same_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "evaluation_run_id", "company_id"],
            [
                "diagnostic_evaluation_runs.tenant_id",
                "diagnostic_evaluation_runs.id",
                "diagnostic_evaluation_runs.company_id",
            ],
            name="fk_diagnostic_findings_run_same_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "evaluation_run_id", "scope_type"],
            [
                "diagnostic_evaluation_runs.tenant_id",
                "diagnostic_evaluation_runs.id",
                "diagnostic_evaluation_runs.scope_type",
            ],
            name="fk_diagnostic_findings_run_same_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "evaluation_run_id",
            "fingerprint",
            name="uq_diagnostic_findings_run_fingerprint",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_diagnostic_findings_tenant_id"),
    )
    op.create_index(
        "ix_diagnostic_findings_fingerprint",
        "diagnostic_findings",
        ["tenant_id", "fingerprint", "status", "last_observed_at"],
        unique=False,
    )
    op.create_index(
        "ix_diagnostic_findings_rule",
        "diagnostic_findings",
        ["tenant_id", "rule_definition_id", "rule_version_number", "detected_at"],
        unique=False,
    )
    op.create_index(
        "ix_diagnostic_findings_scope_status",
        "diagnostic_findings",
        ["tenant_id", "company_id", "branch_id", "status", "severity"],
        unique=False,
    )
    op.create_table(
        "diagnostic_suppressions",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("company_id", UUID, nullable=True),
        sa.Column("branch_id", UUID, nullable=True),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("suppression_type", sa.String(length=24), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("rule_definition_id", UUID, nullable=True),
        sa.Column("rule_ownership_type", sa.String(length=16), nullable=True),
        sa.Column("rule_tenant_id", UUID, nullable=True),
        sa.Column("diagnostic_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("reason_code", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("source_reference", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", UUID, nullable=True),
        sa.Column("revoked_by_user_id", UUID, nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("audit_event_id", UUID, nullable=True),
        sa.Column("id", UUID, nullable=False),
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
            "(scope_type = 'tenant' AND company_id IS NULL AND branch_id IS NULL) OR (scope_type = 'company' AND company_id IS NOT NULL AND branch_id IS NULL) OR (scope_type = 'branch' AND company_id IS NOT NULL AND branch_id IS NOT NULL)",
            name="ck_diagnostic_suppressions_scope",
        ),
        sa.CheckConstraint(
            "(status <> 'expired' OR expires_at IS NOT NULL) AND (status <> 'revoked' OR revoked_at IS NOT NULL)",
            name="ck_diagnostic_suppressions_lifecycle",
        ),
        sa.CheckConstraint(
            "(suppression_type = 'cooldown' AND source = 'engine') OR (suppression_type = 'manual' AND source = 'user') OR (suppression_type = 'rule_exception' AND source = 'configuration')",
            name="ck_diagnostic_suppressions_type_source",
        ),
        sa.CheckConstraint(
            "(target_type = 'rule' AND rule_definition_id IS NOT NULL AND rule_ownership_type IS NOT NULL AND diagnostic_fingerprint IS NULL) OR (target_type = 'fingerprint' AND rule_definition_id IS NULL AND rule_ownership_type IS NULL AND rule_tenant_id IS NULL AND diagnostic_fingerprint IS NOT NULL)",
            name="ck_diagnostic_suppressions_target",
        ),
        sa.CheckConstraint(
            "diagnostic_fingerprint IS NULL OR diagnostic_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_diagnostic_suppressions_fingerprint",
        ),
        sa.CheckConstraint(
            "reason_code IN ('repeat_window','authorized_manual','maintenance','known_exception','data_quality')",
            name="ck_diagnostic_suppressions_reason",
        ),
        sa.CheckConstraint(
            "scope_type IN ('tenant','company','branch')",
            name="ck_diagnostic_suppressions_scope_type",
        ),
        sa.CheckConstraint(
            "source IN ('engine','user','configuration')", name="ck_diagnostic_suppressions_source"
        ),
        sa.CheckConstraint(
            "status IN ('active','expired','revoked')", name="ck_diagnostic_suppressions_status"
        ),
        sa.CheckConstraint(
            "suppression_type IN ('cooldown','manual','rule_exception')",
            name="ck_diagnostic_suppressions_type",
        ),
        sa.CheckConstraint(
            "target_type <> 'rule' OR (rule_ownership_type = 'system' AND rule_tenant_id IS NULL) OR (rule_ownership_type = 'tenant' AND rule_tenant_id = tenant_id)",
            name="ck_diagnostic_suppressions_rule_ownership",
        ),
        sa.CheckConstraint(
            "target_type IN ('rule','fingerprint')", name="ck_diagnostic_suppressions_target_type"
        ),
        sa.CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at", name="ck_diagnostic_suppressions_period"
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at >= starts_at",
            name="ck_diagnostic_suppressions_expiration",
        ),
        sa.ForeignKeyConstraint(["audit_event_id"], ["audit_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["rule_definition_id", "rule_ownership_type"],
            ["diagnostic_rule_definitions.id", "diagnostic_rule_definitions.ownership_type"],
            name="fk_diagnostic_suppressions_rule_ownership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rule_tenant_id", "rule_definition_id", "rule_ownership_type"],
            [
                "diagnostic_rule_definitions.tenant_id",
                "diagnostic_rule_definitions.id",
                "diagnostic_rule_definitions.ownership_type",
            ],
            name="fk_diagnostic_suppressions_tenant_rule",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_diagnostic_suppressions_branch_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            name="fk_diagnostic_suppressions_company_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_diagnostic_suppressions_tenant_id"),
    )
    op.create_index(
        "ix_diagnostic_suppressions_active",
        "diagnostic_suppressions",
        ["tenant_id", "company_id", "branch_id", "status", "expires_at"],
        unique=False,
    )
    op.create_index(
        "uq_diagnostic_suppressions_target_period",
        "diagnostic_suppressions",
        [
            "tenant_id",
            "suppression_type",
            "target_type",
            "rule_definition_id",
            "diagnostic_fingerprint",
            "company_id",
            "branch_id",
            "starts_at",
        ],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    op.create_table(
        "diagnostic_action_recommendations",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("diagnostic_id", UUID, nullable=False),
        sa.Column("catalog_entry_id", UUID, nullable=False),
        sa.Column("suggested_priority", sa.Integer(), nullable=False),
        sa.Column("stable_order", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False),
        sa.Column("reviewed_by_user_id", UUID, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", UUID, nullable=False),
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
            "(status = 'reviewed' AND reviewed_at IS NOT NULL) OR status <> 'reviewed'",
            name="ck_diagnostic_action_recommendations_reviewed_at",
        ),
        sa.CheckConstraint(
            "status IN ('suggested','reviewed','dismissed','expired')",
            name="ck_diagnostic_action_recommendations_status",
        ),
        sa.CheckConstraint(
            "requires_human_review = true", name="ck_diagnostic_action_recommendations_human_review"
        ),
        sa.CheckConstraint("stable_order >= 0", name="ck_diagnostic_action_recommendations_order"),
        sa.CheckConstraint(
            "suggested_priority IN (1,2,3,4)", name="ck_diagnostic_action_recommendations_priority"
        ),
        sa.ForeignKeyConstraint(
            ["catalog_entry_id"], ["diagnostic_action_catalog_entries.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "diagnostic_id"],
            ["diagnostic_findings.tenant_id", "diagnostic_findings.id"],
            name="fk_diagnostic_action_recommendations_finding_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "diagnostic_id",
            "catalog_entry_id",
            name="uq_diagnostic_action_recommendations_entry",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "diagnostic_id",
            "stable_order",
            name="uq_diagnostic_action_recommendations_order",
        ),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_diagnostic_action_recommendations_tenant_id"
        ),
    )
    op.create_index(
        "ix_diagnostic_action_recommendations_finding",
        "diagnostic_action_recommendations",
        ["tenant_id", "diagnostic_id", "status", "stable_order"],
        unique=False,
    )
    op.create_table(
        "diagnostic_evidences",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("diagnostic_id", UUID, nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("kpi_code", sa.String(length=140), nullable=False),
        sa.Column("observed_value", sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column("reference_value", sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dimension_type", sa.String(length=80), nullable=True),
        sa.Column("dimension_member_key", sa.String(length=300), nullable=True),
        sa.Column("direction", sa.String(length=24), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("analytics_data_version", sa.BigInteger(), nullable=False),
        sa.Column("formula_version", sa.Integer(), nullable=False),
        sa.Column("detail_snapshot", JSONB, nullable=False),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("stable_order", sa.Integer(), nullable=False),
        sa.Column("id", UUID, nullable=False),
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
            "direction IN ('above','below','equal','increasing','decreasing','mixed','not_applicable')",
            name="ck_diagnostic_evidences_direction",
        ),
        sa.CheckConstraint("evidence_hash ~ '^[0-9a-f]{64}$'", name="ck_diagnostic_evidences_hash"),
        sa.CheckConstraint(
            "evidence_type IN ('kpi_value','comparison','trend','threshold','data_quality','lineage')",
            name="ck_diagnostic_evidences_type",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(detail_snapshot) = 'object'",
            name="ck_diagnostic_evidences_detail_snapshot",
        ),
        sa.CheckConstraint(
            "source_type IN ('analytics_kpi','analytics_fact','analytics_aggregate','data_quality','lineage')",
            name="ck_diagnostic_evidences_source",
        ),
        sa.CheckConstraint(
            "analytics_data_version >= 0 AND formula_version >= 1",
            name="ck_diagnostic_evidences_versions",
        ),
        sa.CheckConstraint("period_end >= period_start", name="ck_diagnostic_evidences_period"),
        sa.CheckConstraint("stable_order >= 0", name="ck_diagnostic_evidences_order"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "diagnostic_id"],
            ["diagnostic_findings.tenant_id", "diagnostic_findings.id"],
            name="fk_diagnostic_evidences_finding_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "diagnostic_id", "evidence_hash", name="uq_diagnostic_evidences_hash"
        ),
        sa.UniqueConstraint(
            "tenant_id", "diagnostic_id", "id", name="uq_diagnostic_evidences_tenant_diagnostic_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "diagnostic_id", "stable_order", name="uq_diagnostic_evidences_order"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_diagnostic_evidences_tenant_id"),
    )
    op.create_index(
        "ix_diagnostic_evidences_finding",
        "diagnostic_evidences",
        ["tenant_id", "diagnostic_id", "stable_order"],
        unique=False,
    )
    op.create_index(
        "ix_diagnostic_evidences_kpi_period",
        "diagnostic_evidences",
        ["tenant_id", "kpi_code", "period_start", "period_end"],
        unique=False,
    )
    op.create_table(
        "diagnostic_hypotheses",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("diagnostic_id", UUID, nullable=False),
        sa.Column("hypothesis_code", sa.String(length=140), nullable=False),
        sa.Column("definition_snapshot", JSONB, nullable=False),
        sa.Column("evaluation_status", sa.String(length=24), nullable=False),
        sa.Column("confidence_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("supporting_evidence_count", sa.Integer(), nullable=False),
        sa.Column("contradicting_evidence_count", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("logic_version", sa.String(length=40), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", UUID, nullable=False),
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
            "(evaluation_status = 'not_evaluated' AND evaluated_at IS NULL) OR (evaluation_status <> 'not_evaluated' AND evaluated_at IS NOT NULL)",
            name="ck_diagnostic_hypotheses_evaluation_time",
        ),
        sa.CheckConstraint(
            "evaluation_status IN ('supported','contradicted','inconclusive','not_evaluated')",
            name="ck_diagnostic_hypotheses_status",
        ),
        sa.CheckConstraint(
            "hypothesis_code ~ '^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$'",
            name="ck_diagnostic_hypotheses_code",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(definition_snapshot) = 'object'",
            name="ck_diagnostic_hypotheses_definition_snapshot",
        ),
        sa.CheckConstraint(
            "confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1",
            name="ck_diagnostic_hypotheses_confidence",
        ),
        sa.CheckConstraint("rank >= 1", name="ck_diagnostic_hypotheses_rank"),
        sa.CheckConstraint(
            "supporting_evidence_count >= 0 AND contradicting_evidence_count >= 0",
            name="ck_diagnostic_hypotheses_evidence_counts",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "diagnostic_id"],
            ["diagnostic_findings.tenant_id", "diagnostic_findings.id"],
            name="fk_diagnostic_hypotheses_finding_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "diagnostic_id",
            "hypothesis_code",
            "logic_version",
            name="uq_diagnostic_hypotheses_definition",
        ),
        sa.UniqueConstraint(
            "tenant_id", "diagnostic_id", "id", name="uq_diagnostic_hypotheses_tenant_diagnostic_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "diagnostic_id", "rank", name="uq_diagnostic_hypotheses_rank"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_diagnostic_hypotheses_tenant_id"),
    )
    op.create_index(
        "ix_diagnostic_hypotheses_finding",
        "diagnostic_hypotheses",
        ["tenant_id", "diagnostic_id", "evaluation_status", "rank"],
        unique=False,
    )
    op.create_table(
        "diagnostic_incidents",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("company_id", UUID, nullable=True),
        sa.Column("branch_id", UUID, nullable=True),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("incident_code", sa.String(length=140), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("aggregate_severity", sa.String(length=16), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("first_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("diagnostic_count", sa.Integer(), nullable=False),
        sa.Column("primary_diagnostic_id", UUID, nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", UUID, nullable=False),
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
            "(scope_type = 'tenant' AND company_id IS NULL AND branch_id IS NULL) OR (scope_type = 'company' AND company_id IS NOT NULL AND branch_id IS NULL) OR (scope_type = 'branch' AND company_id IS NOT NULL AND branch_id IS NOT NULL)",
            name="ck_diagnostic_incidents_scope",
        ),
        sa.CheckConstraint(
            "(status <> 'acknowledged' OR acknowledged_at IS NOT NULL) AND (status <> 'resolved' OR resolved_at IS NOT NULL) AND (status <> 'closed' OR closed_at IS NOT NULL)",
            name="ck_diagnostic_incidents_lifecycle",
        ),
        sa.CheckConstraint(
            "aggregate_severity IN ('info','low','medium','high','critical')",
            name="ck_diagnostic_incidents_severity",
        ),
        sa.CheckConstraint(
            "domain IN ('inventory','sales','margin','purchases','suppliers','operations')",
            name="ck_diagnostic_incidents_domain",
        ),
        sa.CheckConstraint(
            "fingerprint ~ '^[0-9a-f]{64}$'", name="ck_diagnostic_incidents_fingerprint"
        ),
        sa.CheckConstraint(
            "incident_code ~ '^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$'",
            name="ck_diagnostic_incidents_code",
        ),
        sa.CheckConstraint(
            "scope_type IN ('tenant','company','branch')", name="ck_diagnostic_incidents_scope_type"
        ),
        sa.CheckConstraint(
            "status IN ('open','acknowledged','resolved','closed')",
            name="ck_diagnostic_incidents_status",
        ),
        sa.CheckConstraint("diagnostic_count >= 1", name="ck_diagnostic_incidents_count"),
        sa.CheckConstraint(
            "last_event_at >= first_event_at", name="ck_diagnostic_incidents_period"
        ),
        sa.CheckConstraint("priority IN (1,2,3,4)", name="ck_diagnostic_incidents_priority"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            name="fk_diagnostic_incidents_branch_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            name="fk_diagnostic_incidents_company_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "primary_diagnostic_id"],
            ["diagnostic_findings.tenant_id", "diagnostic_findings.id"],
            name="fk_diagnostic_incidents_primary_finding_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_diagnostic_incidents_tenant_id"),
        sa.UniqueConstraint("tenant_id", "incident_code", name="uq_diagnostic_incidents_code"),
    )
    op.create_index(
        "ix_diagnostic_incidents_fingerprint",
        "diagnostic_incidents",
        ["tenant_id", "fingerprint", "last_event_at"],
        unique=False,
    )
    op.create_index(
        "ix_diagnostic_incidents_scope_status",
        "diagnostic_incidents",
        ["tenant_id", "company_id", "branch_id", "status", "aggregate_severity"],
        unique=False,
    )
    op.create_table(
        "diagnostic_hypothesis_evidences",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("diagnostic_id", UUID, nullable=False),
        sa.Column("hypothesis_id", UUID, nullable=False),
        sa.Column("evidence_id", UUID, nullable=False),
        sa.Column("relation", sa.String(length=16), nullable=False),
        sa.Column("stable_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "relation IN ('supports','contradicts')",
            name="ck_diagnostic_hypothesis_evidences_relation",
        ),
        sa.CheckConstraint("stable_order >= 0", name="ck_diagnostic_hypothesis_evidences_order"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "diagnostic_id", "evidence_id"],
            [
                "diagnostic_evidences.tenant_id",
                "diagnostic_evidences.diagnostic_id",
                "diagnostic_evidences.id",
            ],
            name="fk_diagnostic_hypothesis_evidences_evidence_same_diagnostic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "diagnostic_id", "hypothesis_id"],
            [
                "diagnostic_hypotheses.tenant_id",
                "diagnostic_hypotheses.diagnostic_id",
                "diagnostic_hypotheses.id",
            ],
            name="fk_diagnostic_hypothesis_evidences_hypothesis_same_diagnostic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "hypothesis_id", "evidence_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "hypothesis_id",
            "relation",
            "stable_order",
            name="uq_diagnostic_hypothesis_evidences_order",
        ),
    )
    op.create_index(
        "ix_diagnostic_hypothesis_evidences_evidence",
        "diagnostic_hypothesis_evidences",
        ["tenant_id", "evidence_id"],
        unique=False,
    )
    op.create_table(
        "diagnostic_incident_memberships",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("incident_id", UUID, nullable=False),
        sa.Column("diagnostic_id", UUID, nullable=False),
        sa.Column("stable_order", sa.Integer(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("stable_order >= 0", name="ck_diagnostic_incident_memberships_order"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "diagnostic_id"],
            ["diagnostic_findings.tenant_id", "diagnostic_findings.id"],
            name="fk_diagnostic_incident_memberships_finding_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "incident_id"],
            ["diagnostic_incidents.tenant_id", "diagnostic_incidents.id"],
            name="fk_diagnostic_incident_memberships_incident_same_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "incident_id", "diagnostic_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "incident_id",
            "stable_order",
            name="uq_diagnostic_incident_memberships_order",
        ),
    )
    op.create_index(
        "ix_diagnostic_incident_memberships_finding",
        "diagnostic_incident_memberships",
        ["tenant_id", "diagnostic_id"],
        unique=False,
    )

    _seed_permissions()
    _seed_action_catalog()

    for table in TENANT_TABLES:
        _enable_tenant_rls(table)
    _enable_rule_definition_rls()
    _enable_rule_version_rls()
    for table in GLOBAL_CATALOG_TABLES:
        _enable_global_catalog_rls(table)


def _drop_rls_policies() -> None:
    for table in TENANT_TABLES:
        op.execute(f'DROP POLICY IF EXISTS "{table}_tenant_policy" ON "{table}"')
    for table in ("diagnostic_rule_definitions", "diagnostic_rule_versions"):
        for operation in ("select", "insert", "update", "delete"):
            op.execute(f'DROP POLICY IF EXISTS "{table}_{operation}_policy" ON "{table}"')
    for table in GLOBAL_CATALOG_TABLES:
        op.execute(f'DROP POLICY IF EXISTS "{table}_select_policy" ON "{table}"')


def downgrade() -> None:
    _drop_rls_policies()
    op.execute("ALTER TABLE role_permissions DISABLE TRIGGER role_permissions_protect_system")
    keys_sql = ",".join(f"'{key}'" for key in _ALL_DIAGNOSTIC_PERMISSION_KEYS)
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id IN "
        f"(SELECT id FROM permissions WHERE key IN ({keys_sql}))"
    )
    op.execute(f"DELETE FROM permissions WHERE key IN ({keys_sql})")
    op.execute("ALTER TABLE role_permissions ENABLE TRIGGER role_permissions_protect_system")

    op.drop_table("diagnostic_incident_memberships")
    op.drop_table("diagnostic_hypothesis_evidences")
    op.drop_table("diagnostic_incidents")
    op.drop_table("diagnostic_suppressions")
    op.drop_table("diagnostic_action_recommendations")
    op.drop_table("diagnostic_hypotheses")
    op.drop_table("diagnostic_evidences")
    op.drop_table("diagnostic_findings")
    op.drop_table("diagnostic_rule_configurations")
    op.drop_table("diagnostic_evaluation_runs")
    op.drop_table("diagnostic_action_catalog_entries")
    op.drop_constraint(
        "fk_diagnostic_rule_definitions_current_version",
        "diagnostic_rule_definitions",
        type_="foreignkey",
    )
    op.drop_table("diagnostic_rule_versions")
    op.drop_table("diagnostic_rule_definitions")
    op.drop_table("diagnostic_action_catalog_snapshots")
