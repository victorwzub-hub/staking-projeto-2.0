from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pharma_api.domain.diagnostics.actions import (
    ACTION_DOMAINS,
    ACTION_PRIORITIES,
    ACTION_STATUSES,
)
from pharma_api.domain.diagnostics.conditions import (
    MAX_COOLDOWN_HOURS,
    MIN_COOLDOWN_HOURS,
    SEVERITIES,
)
from pharma_api.infrastructure.db.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionMixin,
)

RULE_OWNERSHIP_TYPES = ("system", "tenant")
RULE_LIFECYCLE_STATUSES = ("draft", "active", "deprecated", "archived")
RULE_VERSION_STATUSES = ("draft", "published", "retired")
RULE_VERSION_POLICIES = ("follow_published", "pinned")
RULE_SCOPE_TYPES = ("tenant", "company", "branch")
ACTION_CATALOG_STATUSES = ("draft", "published", "retired")
PUBLICATION_SOURCES = ("system", "user", "migration")
HUMAN_REVIEW_EXECUTION_MODE = "human_review_required"
HASH_LENGTH = 64

_RULE_DOMAIN_SQL = ",".join(repr(value) for value in ACTION_DOMAINS)
_RULE_OWNERSHIP_SQL = ",".join(repr(value) for value in RULE_OWNERSHIP_TYPES)
_RULE_LIFECYCLE_SQL = ",".join(repr(value) for value in RULE_LIFECYCLE_STATUSES)
_RULE_VERSION_STATUS_SQL = ",".join(repr(value) for value in RULE_VERSION_STATUSES)
_RULE_VERSION_POLICY_SQL = ",".join(repr(value) for value in RULE_VERSION_POLICIES)
_RULE_SCOPE_SQL = ",".join(repr(value) for value in RULE_SCOPE_TYPES)
_ACTION_PRIORITY_SQL = ",".join(str(value) for value in ACTION_PRIORITIES)
_ACTION_STATUS_SQL = ",".join(repr(value) for value in ACTION_STATUSES)
_ACTION_CATALOG_STATUS_SQL = ",".join(repr(value) for value in ACTION_CATALOG_STATUSES)
_SEVERITY_SQL = ",".join(repr(value) for value in SEVERITIES)
_PUBLICATION_SOURCE_SQL = ",".join(repr(value) for value in PUBLICATION_SOURCES)


class DiagnosticRuleDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Stable identity for a deterministic system or tenant-owned rule."""

    __tablename__ = "diagnostic_rule_definitions"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "ownership_type",
            name="uq_diagnostic_rule_definitions_id_ownership",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            "ownership_type",
            name="uq_diagnostic_rule_definitions_tenant_id_ownership",
        ),
        CheckConstraint(
            f"domain IN ({_RULE_DOMAIN_SQL})",
            name="ck_diagnostic_rule_definitions_domain",
        ),
        CheckConstraint(
            f"ownership_type IN ({_RULE_OWNERSHIP_SQL})",
            name="ck_diagnostic_rule_definitions_ownership_type",
        ),
        CheckConstraint(
            "(ownership_type = 'system' AND tenant_id IS NULL) OR "
            "(ownership_type = 'tenant' AND tenant_id IS NOT NULL)",
            name="ck_diagnostic_rule_definitions_ownership",
        ),
        CheckConstraint(
            f"lifecycle_status IN ({_RULE_LIFECYCLE_SQL})",
            name="ck_diagnostic_rule_definitions_lifecycle_status",
        ),
        CheckConstraint(
            "code ~ '^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$'",
            name="ck_diagnostic_rule_definitions_code",
        ),
        CheckConstraint(
            "current_published_version_number IS NULL OR current_published_version_number >= 1",
            name="ck_diagnostic_rule_definitions_current_version",
        ),
        ForeignKeyConstraint(
            ["id", "current_published_version_number"],
            [
                "diagnostic_rule_versions.rule_definition_id",
                "diagnostic_rule_versions.version_number",
            ],
            ondelete="RESTRICT",
            use_alter=True,
            name="fk_diagnostic_rule_definitions_current_version",
        ),
        Index(
            "uq_diagnostic_rule_definitions_system_code",
            "code",
            unique=True,
            postgresql_where=text("tenant_id IS NULL"),
        ),
        Index(
            "uq_diagnostic_rule_definitions_tenant_code",
            "tenant_id",
            "code",
            unique=True,
            postgresql_where=text("tenant_id IS NOT NULL"),
        ),
        Index(
            "ix_diagnostic_rule_definitions_catalog",
            "domain",
            "lifecycle_status",
            "code",
        ),
    )

    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(140), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    ownership_type: Mapped[str] = mapped_column(String(16), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    current_published_version_number: Mapped[int | None] = mapped_column(Integer)
    enabled_by_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class DiagnosticRuleVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable publication candidate for one stable diagnostic rule."""

    __tablename__ = "diagnostic_rule_versions"
    __table_args__ = (
        UniqueConstraint(
            "rule_definition_id",
            "version_number",
            name="uq_diagnostic_rule_versions_definition_version",
        ),
        CheckConstraint(
            "version_number >= 1",
            name="ck_diagnostic_rule_versions_version_number",
        ),
        CheckConstraint(
            f"status IN ({_RULE_VERSION_STATUS_SQL})",
            name="ck_diagnostic_rule_versions_status",
        ),
        CheckConstraint(
            f"publication_source IN ({_PUBLICATION_SOURCE_SQL})",
            name="ck_diagnostic_rule_versions_publication_source",
        ),
        CheckConstraint(
            "effective_to IS NULL OR "
            "(effective_from IS NOT NULL AND effective_to > effective_from)",
            name="ck_diagnostic_rule_versions_period",
        ),
        CheckConstraint(
            "status <> 'published' OR (published_at IS NOT NULL AND effective_from IS NOT NULL)",
            name="ck_diagnostic_rule_versions_publication",
        ),
        CheckConstraint(
            f"condition_hash ~ '^[0-9a-f]{{{HASH_LENGTH}}}$'",
            name="ck_diagnostic_rule_versions_condition_hash",
        ),
        CheckConstraint(
            f"definition_hash ~ '^[0-9a-f]{{{HASH_LENGTH}}}$'",
            name="ck_diagnostic_rule_versions_definition_hash",
        ),
        CheckConstraint(
            "jsonb_typeof(condition_document) = 'object'",
            name="ck_diagnostic_rule_versions_condition_document",
        ),
        CheckConstraint(
            "jsonb_typeof(kpi_codes) = 'array'",
            name="ck_diagnostic_rule_versions_kpi_codes",
        ),
        CheckConstraint(
            "jsonb_typeof(action_codes) = 'array'",
            name="ck_diagnostic_rule_versions_action_codes",
        ),
        CheckConstraint(
            "jsonb_typeof(controls) = 'object'",
            name="ck_diagnostic_rule_versions_controls",
        ),
        CheckConstraint(
            "jsonb_typeof(evidence_metadata) = 'object'",
            name="ck_diagnostic_rule_versions_evidence_metadata",
        ),
        CheckConstraint(
            "jsonb_typeof(hypothesis_metadata) = 'object'",
            name="ck_diagnostic_rule_versions_hypothesis_metadata",
        ),
        Index(
            "ix_diagnostic_rule_versions_catalog",
            "rule_definition_id",
            "status",
            "version_number",
        ),
        Index(
            "ix_diagnostic_rule_versions_effective",
            "status",
            "effective_from",
            "effective_to",
        ),
    )

    rule_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("diagnostic_rule_definitions.id", ondelete="CASCADE")
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    condition_document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    condition_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False)
    kpi_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    action_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    controls: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    evidence_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    hypothesis_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publication_source: Mapped[str] = mapped_column(String(24), nullable=False, default="system")
    published_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_revision: Mapped[str | None] = mapped_column(String(120))


class DiagnosticActionCatalogSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Global immutable snapshot header for the deterministic action catalog."""

    __tablename__ = "diagnostic_action_catalog_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "catalog_version",
            name="uq_diagnostic_action_catalog_snapshots_version",
        ),
        UniqueConstraint(
            "catalog_hash",
            name="uq_diagnostic_action_catalog_snapshots_hash",
        ),
        CheckConstraint(
            "catalog_version >= 1",
            name="ck_diagnostic_action_catalog_snapshots_version",
        ),
        CheckConstraint(
            f"status IN ({_ACTION_CATALOG_STATUS_SQL})",
            name="ck_diagnostic_action_catalog_snapshots_status",
        ),
        CheckConstraint(
            f"catalog_hash ~ '^[0-9a-f]{{{HASH_LENGTH}}}$'",
            name="ck_diagnostic_action_catalog_snapshots_hash",
        ),
        CheckConstraint(
            "effective_to IS NULL OR "
            "(effective_from IS NOT NULL AND effective_to > effective_from)",
            name="ck_diagnostic_action_catalog_snapshots_period",
        ),
        CheckConstraint(
            "status <> 'published' OR (published_at IS NOT NULL AND effective_from IS NOT NULL)",
            name="ck_diagnostic_action_catalog_snapshots_publication",
        ),
        CheckConstraint(
            "is_current = false OR status = 'published'",
            name="ck_diagnostic_action_catalog_snapshots_current",
        ),
        Index(
            "uq_diagnostic_action_catalog_snapshots_current",
            "is_current",
            unique=True,
            postgresql_where=text("is_current = true"),
        ),
        Index(
            "ix_diagnostic_action_catalog_snapshots_status",
            "status",
            "effective_from",
        ),
    )

    catalog_version: Mapped[int] = mapped_column(Integer, nullable=False)
    catalog_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_revision: Mapped[str] = mapped_column(String(120), nullable=False)


class DiagnosticActionCatalogEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Versioned advisory action entry inside one global catalog snapshot."""

    __tablename__ = "diagnostic_action_catalog_entries"
    __table_args__ = (
        UniqueConstraint(
            "catalog_snapshot_id",
            "action_code",
            name="uq_diagnostic_action_catalog_entries_snapshot_code",
        ),
        CheckConstraint(
            "action_version >= 1",
            name="ck_diagnostic_action_catalog_entries_version",
        ),
        CheckConstraint(
            f"domain IN ({_RULE_DOMAIN_SQL})",
            name="ck_diagnostic_action_catalog_entries_domain",
        ),
        CheckConstraint(
            f"default_priority IN ({_ACTION_PRIORITY_SQL})",
            name="ck_diagnostic_action_catalog_entries_priority",
        ),
        CheckConstraint(
            f"status IN ({_ACTION_STATUS_SQL})",
            name="ck_diagnostic_action_catalog_entries_status",
        ),
        CheckConstraint(
            "action_code ~ '^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$'",
            name="ck_diagnostic_action_catalog_entries_code",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_diagnostic_action_catalog_entries_period",
        ),
        CheckConstraint(
            f"definition_hash ~ '^[0-9a-f]{{{HASH_LENGTH}}}$'",
            name="ck_diagnostic_action_catalog_entries_definition_hash",
        ),
        CheckConstraint(
            "jsonb_typeof(definition_snapshot) = 'object'",
            name="ck_diagnostic_action_catalog_entries_snapshot",
        ),
        CheckConstraint(
            f"execution_mode = '{HUMAN_REVIEW_EXECUTION_MODE}'",
            name="ck_diagnostic_action_catalog_entries_execution_mode",
        ),
        CheckConstraint(
            "requires_human_review = true",
            name="ck_diagnostic_action_catalog_entries_human_review",
        ),
        CheckConstraint(
            "COALESCE(definition_snapshot ->> 'execution_mode', '') = 'human_review_required'",
            name="ck_diagnostic_action_catalog_entries_snapshot_execution_mode",
        ),
        CheckConstraint(
            "COALESCE(definition_snapshot ->> 'allows_automatic_financial_execution', '') "
            "= 'false'",
            name="ck_diagnostic_action_catalog_entries_no_financial_execution",
        ),
        Index(
            "ix_diagnostic_action_catalog_entries_history",
            "action_code",
            "action_version",
        ),
        Index(
            "ix_diagnostic_action_catalog_entries_catalog",
            "catalog_snapshot_id",
            "domain",
            "status",
            "default_priority",
        ),
    )

    catalog_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("diagnostic_action_catalog_snapshots.id", ondelete="CASCADE")
    )
    action_code: Mapped[str] = mapped_column(String(100), nullable=False)
    action_version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    default_priority: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    definition_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False)
    execution_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default=HUMAN_REVIEW_EXECUTION_MODE
    )
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DiagnosticRuleConfiguration(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    VersionMixin,
    Base,
):
    """Tenant-owned activation and safe scope configuration for a known rule."""

    __tablename__ = "diagnostic_rule_configurations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_diagnostic_rule_configurations_tenant_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_diagnostic_rule_configurations_company_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_diagnostic_rule_configurations_branch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["rule_definition_id", "rule_ownership_type"],
            ["diagnostic_rule_definitions.id", "diagnostic_rule_definitions.ownership_type"],
            ondelete="RESTRICT",
            name="fk_diagnostic_rule_configurations_rule_ownership",
        ),
        ForeignKeyConstraint(
            ["rule_tenant_id", "rule_definition_id", "rule_ownership_type"],
            [
                "diagnostic_rule_definitions.tenant_id",
                "diagnostic_rule_definitions.id",
                "diagnostic_rule_definitions.ownership_type",
            ],
            ondelete="RESTRICT",
            name="fk_diagnostic_rule_configurations_tenant_rule",
        ),
        ForeignKeyConstraint(
            ["rule_definition_id", "selected_version_number"],
            [
                "diagnostic_rule_versions.rule_definition_id",
                "diagnostic_rule_versions.version_number",
            ],
            ondelete="RESTRICT",
            name="fk_diagnostic_rule_configurations_selected_version",
        ),
        CheckConstraint(
            f"scope_type IN ({_RULE_SCOPE_SQL})",
            name="ck_diagnostic_rule_configurations_scope_type",
        ),
        CheckConstraint(
            "(scope_type = 'tenant' AND company_id IS NULL AND branch_id IS NULL) OR "
            "(scope_type = 'company' AND company_id IS NOT NULL AND branch_id IS NULL) OR "
            "(scope_type = 'branch' AND company_id IS NOT NULL AND branch_id IS NOT NULL)",
            name="ck_diagnostic_rule_configurations_scope",
        ),
        CheckConstraint(
            f"rule_ownership_type IN ({_RULE_OWNERSHIP_SQL})",
            name="ck_diagnostic_rule_configurations_rule_ownership_type",
        ),
        CheckConstraint(
            "(rule_ownership_type = 'system' AND rule_tenant_id IS NULL) OR "
            "(rule_ownership_type = 'tenant' AND rule_tenant_id = tenant_id)",
            name="ck_diagnostic_rule_configurations_rule_ownership",
        ),
        CheckConstraint(
            f"version_policy IN ({_RULE_VERSION_POLICY_SQL})",
            name="ck_diagnostic_rule_configurations_version_policy",
        ),
        CheckConstraint(
            "(version_policy = 'follow_published' AND selected_version_number IS NULL) OR "
            "(version_policy = 'pinned' AND selected_version_number IS NOT NULL)",
            name="ck_diagnostic_rule_configurations_version_selection",
        ),
        CheckConstraint(
            "selected_version_number IS NULL OR selected_version_number >= 1",
            name="ck_diagnostic_rule_configurations_selected_version",
        ),
        CheckConstraint(
            f"cooldown_hours IS NULL OR cooldown_hours BETWEEN {MIN_COOLDOWN_HOURS} "
            f"AND {MAX_COOLDOWN_HOURS}",
            name="ck_diagnostic_rule_configurations_cooldown",
        ),
        CheckConstraint(
            f"minimum_severity IN ({_SEVERITY_SQL})",
            name="ck_diagnostic_rule_configurations_minimum_severity",
        ),
        CheckConstraint(
            "active_to IS NULL OR (active_from IS NOT NULL AND active_to > active_from)",
            name="ck_diagnostic_rule_configurations_period",
        ),
        Index(
            "uq_diagnostic_rule_configurations_scope",
            "tenant_id",
            "rule_definition_id",
            "company_id",
            "branch_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        Index(
            "ix_diagnostic_rule_configurations_lookup",
            "tenant_id",
            "company_id",
            "branch_id",
            "enabled",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID | None] = mapped_column()
    branch_id: Mapped[UUID | None] = mapped_column()
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_definition_id: Mapped[UUID] = mapped_column()
    rule_ownership_type: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_tenant_id: Mapped[UUID | None] = mapped_column()
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version_policy: Mapped[str] = mapped_column(
        String(24), nullable=False, default="follow_published"
    )
    selected_version_number: Mapped[int | None] = mapped_column(Integer)
    cooldown_hours: Mapped[int | None] = mapped_column(Integer)
    minimum_severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    active_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
