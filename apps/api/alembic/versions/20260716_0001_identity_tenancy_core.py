"""Create identity, tenancy, RBAC, onboarding and audit foundation.

Revision ID: 20260716_0001
Revises:
Create Date: 2026-07-16
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())

PERMISSIONS: tuple[tuple[str, str, str], ...] = (
    ("platform.admin", "platform", "Administração integral da plataforma"),
    ("tenant.read", "tenant", "Visualizar o tenant ativo"),
    ("tenant.update", "tenant", "Alterar dados do tenant"),
    ("company.create", "tenant", "Criar empresas"),
    ("company.read", "company", "Visualizar empresas"),
    ("company.update", "company", "Alterar empresas"),
    ("company.delete", "company", "Arquivar empresas"),
    ("branch.create", "company", "Criar filiais"),
    ("branch.read", "branch", "Visualizar filiais"),
    ("branch.update", "branch", "Alterar filiais"),
    ("branch.delete", "branch", "Arquivar filiais"),
    ("user.invite", "tenant", "Convidar usuários"),
    ("user.read", "tenant", "Visualizar usuários do tenant"),
    ("user.update", "tenant", "Alterar usuários do tenant"),
    ("membership.manage", "tenant", "Gerenciar memberships"),
    ("team.create", "tenant", "Criar equipes"),
    ("team.read", "tenant", "Visualizar equipes"),
    ("team.update", "tenant", "Alterar equipes"),
    ("team.delete", "tenant", "Excluir equipes"),
    ("role.create", "tenant", "Criar papéis customizados"),
    ("role.read", "tenant", "Visualizar papéis e permissões"),
    ("role.update", "tenant", "Alterar papéis customizados"),
    ("role.delete", "tenant", "Excluir papéis customizados"),
    ("role.assign", "tenant", "Atribuir papéis delegáveis"),
    ("audit.read", "tenant", "Visualizar auditoria"),
    ("session.manage", "tenant", "Gerenciar sessões da própria conta"),
    ("security.read", "tenant", "Visualizar eventos de segurança da própria conta"),
    ("onboarding.manage", "tenant", "Concluir onboarding"),
    ("context.switch", "tenant", "Trocar tenant, empresa ou filial ativa"),
    ("impersonation.start", "platform", "Iniciar impersonation controlada futura"),
)

ROLE_DEFINITIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "platform_admin": ("platform", ("platform.admin",)),
    "tenant_owner": (
        "tenant",
        tuple(
            key for key, _, _ in PERMISSIONS if key not in {"platform.admin", "impersonation.start"}
        ),
    ),
    "tenant_admin": (
        "tenant",
        tuple(
            key
            for key, _, _ in PERMISSIONS
            if key not in {"platform.admin", "impersonation.start", "tenant.update"}
        ),
    ),
    "company_admin": (
        "company",
        (
            "tenant.read",
            "company.read",
            "company.update",
            "branch.create",
            "branch.read",
            "branch.update",
            "branch.delete",
            "user.read",
            "team.read",
            "role.read",
            "audit.read",
            "context.switch",
            "session.manage",
        ),
    ),
    "branch_manager": (
        "branch",
        (
            "tenant.read",
            "company.read",
            "branch.read",
            "branch.update",
            "user.read",
            "team.read",
            "audit.read",
            "context.switch",
            "session.manage",
        ),
    ),
    "analyst": (
        "tenant",
        (
            "tenant.read",
            "company.read",
            "branch.read",
            "user.read",
            "context.switch",
            "session.manage",
        ),
    ),
    "consultant": (
        "tenant",
        (
            "tenant.read",
            "company.read",
            "branch.read",
            "user.read",
            "context.switch",
            "session.manage",
        ),
    ),
    "accountant": (
        "tenant",
        ("tenant.read", "company.read", "branch.read", "context.switch", "session.manage"),
    ),
    "viewer": (
        "tenant",
        ("tenant.read", "company.read", "branch.read", "context.switch", "session.manage"),
    ),
}

RLS_POLICY_TABLES: tuple[str, ...] = (
    "tenants",
    "economic_groups",
    "companies",
    "branches",
    "memberships",
    "teams",
    "team_memberships",
    "roles",
    "role_permissions",
    "role_assignments",
    "invitations",
    "consent_records",
    "onboarding_progress",
    "audit_events",
)


def _uuid(kind: str, value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"pharma-intelligence:{kind}:{value}"))


def _enable_rls(
    table: str,
    *,
    using: str | None = None,
    check: str | None = None,
) -> None:
    tenant_expression = (
        "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
        "OR current_setting('app.is_platform_admin', true) = 'true'"
    )
    using_expression = using or tenant_expression
    check_expression = check or tenant_expression
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY "{table}_tenant_policy" ON "{table}" '
        f"USING ({using_expression}) WITH CHECK ({check_expression})"
    )


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("normalized_email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("anonymized_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ('pending','active','suspended','anonymized')", name="ck_users_status"
        ),
        sa.UniqueConstraint("normalized_email", name="uq_users_normalized_email"),
    )
    op.create_index("ix_users_status", "users", ["status"])

    op.create_table(
        "user_profiles",
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("locale", sa.String(16), nullable=False, server_default="pt-BR"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="America/Sao_Paulo"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    for table_name in ("email_verification_tokens", "password_reset_tokens"):
        op.create_table(
            table_name,
            sa.Column("id", UUID, primary_key=True),
            sa.Column(
                "user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        )
        op.create_index(f"ix_{table_name}_user", table_name, ["user_id"])
        op.create_index(f"ix_{table_name}_expires", table_name, ["expires_at"])

    op.create_table(
        "tenants",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="onboarding"),
        sa.Column(
            "created_by_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ('onboarding','active','suspended','archived')", name="ck_tenants_status"
        ),
    )
    op.create_index("ix_tenants_status", "tenants", ["status"])

    op.create_table(
        "economic_groups",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ('active','inactive','archived')", name="ck_economic_groups_status"
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_economic_groups_tenant_name"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_economic_groups_tenant_id_id"),
    )
    op.create_index("ix_economic_groups_tenant", "economic_groups", ["tenant_id"])

    op.create_table(
        "companies",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("economic_group_id", UUID),
        sa.Column("legal_name", sa.String(220), nullable=False),
        sa.Column("trade_name", sa.String(180), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ('active','inactive','archived')", name="ck_companies_status"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "economic_group_id"],
            ["economic_groups.tenant_id", "economic_groups.id"],
            ondelete="RESTRICT",
            name="fk_companies_economic_group_same_tenant",
            use_alter=True,
        ),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_companies_tenant_slug"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_companies_tenant_id_id"),
    )
    op.create_index("ix_companies_tenant", "companies", ["tenant_id"])
    op.create_index("ix_companies_economic_group", "companies", ["economic_group_id"])

    op.create_table(
        "branches",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("status IN ('active','inactive','archived')", name="ck_branches_status"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_branches_company_same_tenant",
        ),
        sa.UniqueConstraint("tenant_id", "company_id", "slug", name="uq_branches_company_slug"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_branches_tenant_id_id"),
    )
    op.create_index("ix_branches_tenant_company", "branches", ["tenant_id", "company_id"])

    op.create_table(
        "memberships",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("title", sa.String(120)),
        sa.Column("joined_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ('pending','active','suspended','revoked')", name="ck_memberships_status"
        ),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_memberships_tenant_id_id"),
    )
    op.create_index("ix_memberships_user_status", "memberships", ["user_id", "status"])
    op.create_index("ix_memberships_tenant_status", "memberships", ["tenant_id", "status"])

    op.create_table(
        "teams",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_teams_tenant_name"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_teams_tenant_id_id"),
    )
    op.create_index("ix_teams_tenant", "teams", ["tenant_id"])

    op.create_table(
        "team_memberships",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("team_id", UUID, nullable=False),
        sa.Column("membership_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["tenant_id", "team_id"],
            ["teams.tenant_id", "teams.id"],
            ondelete="CASCADE",
            name="fk_team_memberships_team_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["memberships.tenant_id", "memberships.id"],
            ondelete="CASCADE",
            name="fk_team_memberships_membership_same_tenant",
        ),
        sa.UniqueConstraint("team_id", "membership_id", name="uq_team_memberships_pair"),
    )
    op.create_index("ix_team_memberships_tenant", "team_memberships", ["tenant_id"])

    op.create_table(
        "permissions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("key", sa.String(120), nullable=False, unique=True),
        sa.Column("scope", sa.String(24), nullable=False),
        sa.Column("description", sa.String(400), nullable=False),
        sa.Column("catalog_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint(
            "scope IN ('platform','tenant','company','branch')", name="ck_permissions_scope"
        ),
    )
    op.create_index("ix_permissions_scope", "permissions", ["scope"])

    op.create_table(
        "roles",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("scope", sa.String(24), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_editable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("description", sa.String(400)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "scope IN ('platform','tenant','company','branch')", name="ck_roles_scope"
        ),
        sa.CheckConstraint(
            "(is_system = true AND tenant_id IS NULL) OR (is_system = false AND tenant_id IS NOT NULL)",
            name="ck_roles_ownership",
        ),
    )
    op.create_index("ix_roles_tenant", "roles", ["tenant_id"])
    op.execute("CREATE UNIQUE INDEX uq_roles_system_slug ON roles (slug) WHERE tenant_id IS NULL")
    op.execute(
        "CREATE UNIQUE INDEX uq_roles_tenant_slug ON roles (tenant_id, slug) WHERE tenant_id IS NOT NULL"
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", UUID, sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "permission_id",
            UUID,
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "role_assignments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("membership_id", UUID, nullable=False),
        sa.Column("role_id", UUID, sa.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("company_id", UUID),
        sa.Column("branch_id", UUID),
        sa.Column(
            "assigned_by_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["memberships.tenant_id", "memberships.id"],
            ondelete="CASCADE",
            name="fk_role_assignments_membership_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_role_assignments_company_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "branch_id"],
            ["branches.tenant_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_role_assignments_branch_same_tenant",
        ),
    )
    op.create_index(
        "ix_role_assignments_tenant_membership", "role_assignments", ["tenant_id", "membership_id"]
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_role_assignments_scope ON role_assignments "
        "(membership_id, role_id, company_id, branch_id) NULLS NOT DISTINCT"
    )

    op.create_table(
        "sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("active_tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="SET NULL")),
        sa.Column("active_company_id", UUID, sa.ForeignKey("companies.id", ondelete="SET NULL")),
        sa.Column("active_branch_id", UUID, sa.ForeignKey("branches.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revocation_reason", sa.String(120)),
        sa.Column("ip_hash", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
    )
    op.create_index("ix_sessions_user_active", "sessions", ["user_id", "revoked_at", "expires_at"])
    op.create_index("ix_sessions_expires", "sessions", ["expires_at"])

    op.create_table(
        "security_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("correlation_id", sa.String(128)),
        sa.Column("ip_hash", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_security_events_user_created", "security_events", ["user_id", "created_at"])
    op.create_index(
        "ix_security_events_type_created", "security_events", ["event_type", "created_at"]
    )

    op.create_table(
        "authentication_attempts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("normalized_email_hash", sa.String(64), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("failure_reason", sa.String(80)),
        sa.Column("ip_hash", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index(
        "ix_auth_attempts_email_created",
        "authentication_attempts",
        ["normalized_email_hash", "created_at"],
    )
    op.create_index(
        "ix_auth_attempts_ip_created", "authentication_attempts", ["ip_hash", "created_at"]
    )

    op.create_table(
        "invitations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("normalized_email", sa.String(320), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("role_id", UUID, sa.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("company_id", UUID),
        sa.Column("branch_id", UUID),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_by_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ('pending','accepted','revoked','expired')", name="ck_invitations_status"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_invitations_company_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "branch_id"],
            ["branches.tenant_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_invitations_branch_same_tenant",
        ),
    )
    op.create_index("ix_invitations_tenant_email", "invitations", ["tenant_id", "normalized_email"])
    op.create_index("ix_invitations_expires", "invitations", ["expires_at"])

    op.create_table(
        "terms_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("document_type", sa.String(60), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("document_type", "version", name="uq_terms_type_version"),
    )

    op.create_table(
        "consent_records",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="SET NULL")),
        sa.Column(
            "terms_version_id",
            UUID,
            sa.ForeignKey("terms_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("ip_hash", sa.String(64)),
        sa.UniqueConstraint("user_id", "terms_version_id", name="uq_consent_user_terms"),
    )
    op.create_index("ix_consent_records_tenant", "consent_records", ["tenant_id"])

    op.create_table(
        "onboarding_progress",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(24), nullable=False, server_default="started"),
        sa.Column("current_step", sa.String(80), nullable=False, server_default="account"),
        sa.Column("data_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ('started','completed','failed')", name="ck_onboarding_status"
        ),
        sa.UniqueConstraint("user_id", name="uq_onboarding_progress_user"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("effective_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="SET NULL")),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="SET NULL")),
        sa.Column("branch_id", UUID, sa.ForeignKey("branches.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("resource_type", sa.String(100)),
        sa.Column("resource_id", sa.String(100)),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("correlation_id", sa.String(128)),
        sa.Column("ip_hash", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("changed_fields", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("justification", sa.Text()),
        sa.Column("metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_audit_events_tenant_created", "audit_events", ["tenant_id", "created_at"])
    op.create_index(
        "ix_audit_events_actor_created", "audit_events", ["actor_user_id", "created_at"]
    )
    op.create_index("ix_audit_events_resource", "audit_events", ["resource_type", "resource_id"])

    op.execute(
        """
        CREATE FUNCTION reject_audit_event_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'audit_events is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_update_delete BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION reject_audit_event_mutation()"
    )
    op.execute(
        """
        CREATE FUNCTION reject_system_role_mutation() RETURNS trigger AS $$
        BEGIN
          IF OLD.is_system THEN
            RAISE EXCEPTION 'system roles are immutable';
          END IF;
          IF TG_OP = 'DELETE' THEN
            RETURN OLD;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER roles_protect_system BEFORE UPDATE OR DELETE ON roles "
        "FOR EACH ROW EXECUTE FUNCTION reject_system_role_mutation()"
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
                "catalog_version": 1,
            }
            for key, scope, description in PERMISSIONS
        ],
    )

    role_table = sa.table(
        "roles",
        sa.column("id", UUID),
        sa.column("tenant_id", UUID),
        sa.column("name", sa.String()),
        sa.column("slug", sa.String()),
        sa.column("scope", sa.String()),
        sa.column("is_system", sa.Boolean()),
        sa.column("is_editable", sa.Boolean()),
        sa.column("description", sa.String()),
        sa.column("version", sa.Integer()),
    )
    op.bulk_insert(
        role_table,
        [
            {
                "id": _uuid("role", slug),
                "tenant_id": None,
                "name": slug.replace("_", " ").title(),
                "slug": slug,
                "scope": scope,
                "is_system": True,
                "is_editable": False,
                "description": f"Papel de sistema {slug}",
                "version": 1,
            }
            for slug, (scope, _) in ROLE_DEFINITIONS.items()
        ],
    )

    role_permission_table = sa.table(
        "role_permissions",
        sa.column("role_id", UUID),
        sa.column("permission_id", UUID),
    )
    op.bulk_insert(
        role_permission_table,
        [
            {"role_id": _uuid("role", role_slug), "permission_id": _uuid("permission", key)}
            for role_slug, (_, permission_keys) in ROLE_DEFINITIONS.items()
            for key in permission_keys
        ],
    )
    op.execute(
        """
        CREATE FUNCTION reject_system_role_permission_mutation() RETURNS trigger AS $$
        BEGIN
          IF (TG_OP IN ('UPDATE', 'DELETE') AND EXISTS (
                SELECT 1 FROM roles WHERE id = OLD.role_id AND is_system
              ))
             OR (TG_OP IN ('INSERT', 'UPDATE') AND EXISTS (
                SELECT 1 FROM roles WHERE id = NEW.role_id AND is_system
              )) THEN
            RAISE EXCEPTION 'system role permissions are immutable';
          END IF;
          IF TG_OP = 'DELETE' THEN
            RETURN OLD;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER role_permissions_protect_system "
        "BEFORE INSERT OR UPDATE OR DELETE ON role_permissions "
        "FOR EACH ROW EXECUTE FUNCTION reject_system_role_permission_mutation()"
    )

    terms_table = sa.table(
        "terms_versions",
        sa.column("id", UUID),
        sa.column("document_type", sa.String()),
        sa.column("version", sa.String()),
        sa.column("content_hash", sa.String()),
        sa.column("effective_at", sa.DateTime(timezone=True)),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        terms_table,
        [
            {
                "id": _uuid("terms", "platform-terms-phase2-staging-v1"),
                "document_type": "platform_terms",
                "version": "phase2-staging-v1",
                "content_hash": sha256(
                    b"PHARMA INTELLIGENCE PHASE 2 STAGING TERMS - LEGAL REVIEW REQUIRED"
                ).hexdigest(),
                "effective_at": datetime(2026, 7, 16, tzinfo=UTC),
                "is_active": True,
            }
        ],
    )

    tenant_expression = (
        "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
        "OR current_setting('app.is_platform_admin', true) = 'true'"
    )
    current_user = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"

    _enable_rls(
        "tenants",
        using=(
            f"id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
            f"OR created_by_user_id = {current_user} "
            f"OR EXISTS (SELECT 1 FROM memberships m WHERE m.tenant_id = tenants.id "
            f"AND m.user_id = {current_user} AND m.status = 'active') "
            "OR current_setting('app.is_platform_admin', true) = 'true'"
        ),
        check=(
            f"created_by_user_id = {current_user} "
            f"OR (id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
            f"AND EXISTS (SELECT 1 FROM memberships m WHERE m.tenant_id = tenants.id "
            f"AND m.user_id = {current_user} AND m.status = 'active')) "
            "OR current_setting('app.is_platform_admin', true) = 'true'"
        ),
    )
    _enable_rls("economic_groups")
    _enable_rls("companies")
    _enable_rls("branches")
    _enable_rls(
        "memberships",
        using=(f"({tenant_expression}) OR user_id = {current_user}"),
        check=tenant_expression,
    )
    _enable_rls("teams")
    _enable_rls("team_memberships")
    _enable_rls(
        "roles",
        using=(
            "tenant_id IS NULL OR tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
            "OR current_setting('app.is_platform_admin', true) = 'true'"
        ),
        check=(
            "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
            "OR current_setting('app.is_platform_admin', true) = 'true'"
        ),
    )
    _enable_rls(
        "role_permissions",
        using=(
            "EXISTS (SELECT 1 FROM roles r WHERE r.id = role_permissions.role_id AND "
            "(r.tenant_id IS NULL OR r.tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
            "OR current_setting('app.is_platform_admin', true) = 'true'))"
        ),
        check=(
            "EXISTS (SELECT 1 FROM roles r WHERE r.id = role_permissions.role_id AND "
            "(r.tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
            "OR current_setting('app.is_platform_admin', true) = 'true'))"
        ),
    )
    _enable_rls("role_assignments")
    _enable_rls(
        "invitations",
        using=(
            f"({tenant_expression}) OR token_hash = current_setting('app.invitation_token_hash', true)"
        ),
        check=tenant_expression,
    )
    _enable_rls(
        "consent_records",
        using=(f"user_id = {current_user} OR ({tenant_expression})"),
        check=(f"user_id = {current_user} OR ({tenant_expression})"),
    )
    _enable_rls(
        "onboarding_progress",
        using=(
            f"user_id = {current_user} OR current_setting('app.is_platform_admin', true) = 'true'"
        ),
        check=(
            f"user_id = {current_user} OR current_setting('app.is_platform_admin', true) = 'true'"
        ),
    )
    audit_user_expression = (
        f"tenant_id IS NULL AND "
        f"(actor_user_id = {current_user} OR effective_user_id = {current_user})"
    )
    _enable_rls(
        "audit_events",
        using=f"({tenant_expression}) OR ({audit_user_expression})",
        check=f"({tenant_expression}) OR ({audit_user_expression})",
    )


def downgrade() -> None:
    for table in RLS_POLICY_TABLES:
        op.execute(f'DROP POLICY IF EXISTS "{table}_tenant_policy" ON "{table}"')

    op.execute("DROP TRIGGER IF EXISTS role_permissions_protect_system ON role_permissions")
    op.execute("DROP TRIGGER IF EXISTS roles_protect_system ON roles")
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_update_delete ON audit_events")

    op.execute("DROP FUNCTION IF EXISTS reject_system_role_permission_mutation()")
    op.execute("DROP FUNCTION IF EXISTS reject_system_role_mutation()")
    op.execute("DROP FUNCTION IF EXISTS reject_audit_event_mutation()")

    for table in (
        "audit_events",
        "onboarding_progress",
        "consent_records",
        "terms_versions",
        "invitations",
        "authentication_attempts",
        "security_events",
        "sessions",
        "role_assignments",
        "role_permissions",
        "roles",
        "permissions",
        "team_memberships",
        "teams",
        "memberships",
        "branches",
        "companies",
        "economic_groups",
        "tenants",
        "password_reset_tokens",
        "email_verification_tokens",
        "user_profiles",
        "users",
    ):
        op.drop_table(table)
