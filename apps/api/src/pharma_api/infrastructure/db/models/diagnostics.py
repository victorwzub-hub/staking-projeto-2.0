from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
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

EVALUATION_TRIGGER_TYPES = ("scheduled", "manual", "data_refresh", "replay")
EVALUATION_STATUSES = (
    "queued",
    "running",
    "completed",
    "completed_with_warnings",
    "failed",
    "cancelled",
)
EVALUATION_ERROR_TYPES = ("validation", "analytics_unavailable", "rule_failure", "internal")
DIAGNOSTIC_STATUSES = ("open", "acknowledged", "resolved", "closed")
EVIDENCE_TYPES = (
    "kpi_value",
    "comparison",
    "trend",
    "threshold",
    "data_quality",
    "lineage",
)
EVIDENCE_DIRECTIONS = (
    "above",
    "below",
    "equal",
    "increasing",
    "decreasing",
    "mixed",
    "not_applicable",
)
EVIDENCE_SOURCES = (
    "analytics_kpi",
    "analytics_fact",
    "analytics_aggregate",
    "data_quality",
    "lineage",
)
HYPOTHESIS_STATUSES = ("supported", "contradicted", "inconclusive", "not_evaluated")
HYPOTHESIS_EVIDENCE_RELATIONS = ("supports", "contradicts")
ACTION_RECOMMENDATION_STATUSES = ("suggested", "reviewed", "dismissed", "expired")
SUPPRESSION_TYPES = ("cooldown", "manual", "rule_exception")
SUPPRESSION_TARGET_TYPES = ("rule", "fingerprint")
SUPPRESSION_REASONS = (
    "repeat_window",
    "authorized_manual",
    "maintenance",
    "known_exception",
    "data_quality",
)
SUPPRESSION_SOURCES = ("engine", "user", "configuration")
SUPPRESSION_STATUSES = ("active", "expired", "revoked")
INCIDENT_STATUSES = ("open", "acknowledged", "resolved", "closed")

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
_EVALUATION_TRIGGER_SQL = ",".join(repr(value) for value in EVALUATION_TRIGGER_TYPES)
_EVALUATION_STATUS_SQL = ",".join(repr(value) for value in EVALUATION_STATUSES)
_EVALUATION_ERROR_SQL = ",".join(repr(value) for value in EVALUATION_ERROR_TYPES)
_DIAGNOSTIC_STATUS_SQL = ",".join(repr(value) for value in DIAGNOSTIC_STATUSES)
_EVIDENCE_TYPE_SQL = ",".join(repr(value) for value in EVIDENCE_TYPES)
_EVIDENCE_DIRECTION_SQL = ",".join(repr(value) for value in EVIDENCE_DIRECTIONS)
_EVIDENCE_SOURCE_SQL = ",".join(repr(value) for value in EVIDENCE_SOURCES)
_HYPOTHESIS_STATUS_SQL = ",".join(repr(value) for value in HYPOTHESIS_STATUSES)
_HYPOTHESIS_EVIDENCE_RELATION_SQL = ",".join(repr(value) for value in HYPOTHESIS_EVIDENCE_RELATIONS)
_ACTION_RECOMMENDATION_STATUS_SQL = ",".join(
    repr(value) for value in ACTION_RECOMMENDATION_STATUSES
)
_SUPPRESSION_TYPE_SQL = ",".join(repr(value) for value in SUPPRESSION_TYPES)
_SUPPRESSION_TARGET_TYPE_SQL = ",".join(repr(value) for value in SUPPRESSION_TARGET_TYPES)
_SUPPRESSION_REASON_SQL = ",".join(repr(value) for value in SUPPRESSION_REASONS)
_SUPPRESSION_SOURCE_SQL = ",".join(repr(value) for value in SUPPRESSION_SOURCES)
_SUPPRESSION_STATUS_SQL = ",".join(repr(value) for value in SUPPRESSION_STATUSES)
_INCIDENT_STATUS_SQL = ",".join(repr(value) for value in INCIDENT_STATUSES)
_SCOPE_COHERENCE_SQL = (
    "(scope_type = 'tenant' AND company_id IS NULL AND branch_id IS NULL) OR "
    "(scope_type = 'company' AND company_id IS NOT NULL AND branch_id IS NULL) OR "
    "(scope_type = 'branch' AND company_id IS NOT NULL AND branch_id IS NOT NULL)"
)


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


class DiagnosticEvaluationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One deterministic evaluation of known rules for a tenant-owned scope."""

    __tablename__ = "diagnostic_evaluation_runs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_diagnostic_evaluation_runs_tenant_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_diagnostic_evaluation_runs_idempotency",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            "scope_type",
            name="uq_diagnostic_evaluation_runs_tenant_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            "company_id",
            name="uq_diagnostic_evaluation_runs_tenant_company",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            "branch_id",
            name="uq_diagnostic_evaluation_runs_tenant_branch",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="RESTRICT",
            name="fk_diagnostic_evaluation_runs_company_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="RESTRICT",
            name="fk_diagnostic_evaluation_runs_branch_same_tenant",
        ),
        CheckConstraint(
            f"scope_type IN ({_RULE_SCOPE_SQL})",
            name="ck_diagnostic_evaluation_runs_scope_type",
        ),
        CheckConstraint(
            _SCOPE_COHERENCE_SQL,
            name="ck_diagnostic_evaluation_runs_scope",
        ),
        CheckConstraint(
            f"trigger_type IN ({_EVALUATION_TRIGGER_SQL})",
            name="ck_diagnostic_evaluation_runs_trigger_type",
        ),
        CheckConstraint(
            f"status IN ({_EVALUATION_STATUS_SQL})",
            name="ck_diagnostic_evaluation_runs_status",
        ),
        CheckConstraint(
            f"error_type IS NULL OR error_type IN ({_EVALUATION_ERROR_SQL})",
            name="ck_diagnostic_evaluation_runs_error_type",
        ),
        CheckConstraint(
            "(status = 'failed' AND error_type IS NOT NULL) OR "
            "(status <> 'failed' AND error_type IS NULL)",
            name="ck_diagnostic_evaluation_runs_error_state",
        ),
        CheckConstraint(
            "window_end >= window_start",
            name="ck_diagnostic_evaluation_runs_window",
        ),
        CheckConstraint(
            "completed_at IS NULL OR (started_at IS NOT NULL AND completed_at >= started_at)",
            name="ck_diagnostic_evaluation_runs_period",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_diagnostic_evaluation_runs_duration",
        ),
        CheckConstraint(
            "analytics_data_version >= 0",
            name="ck_diagnostic_evaluation_runs_data_version",
        ),
        CheckConstraint(
            "rules_evaluated >= 0 AND rules_skipped >= 0 AND "
            "rule_failures >= 0 AND diagnostics_generated >= 0",
            name="ck_diagnostic_evaluation_runs_counters",
        ),
        Index(
            "ix_diagnostic_evaluation_runs_scope_created",
            "tenant_id",
            "company_id",
            "branch_id",
            "created_at",
        ),
        Index(
            "ix_diagnostic_evaluation_runs_status",
            "tenant_id",
            "status",
            "created_at",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID | None] = mapped_column()
    branch_id: Mapped[UUID | None] = mapped_column()
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    engine_version: Mapped[str] = mapped_column(String(40), nullable=False)
    analytics_data_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    requested_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    rules_evaluated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rules_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rule_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    diagnostics_generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_type: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(String(500))


class DiagnosticFinding(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    """Persisted deterministic diagnosis produced by one exact rule version."""

    __tablename__ = "diagnostic_findings"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_diagnostic_findings_tenant_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "evaluation_run_id",
            "fingerprint",
            name="uq_diagnostic_findings_run_fingerprint",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="RESTRICT",
            name="fk_diagnostic_findings_company_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="RESTRICT",
            name="fk_diagnostic_findings_branch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "evaluation_run_id", "scope_type"],
            [
                "diagnostic_evaluation_runs.tenant_id",
                "diagnostic_evaluation_runs.id",
                "diagnostic_evaluation_runs.scope_type",
            ],
            ondelete="RESTRICT",
            name="fk_diagnostic_findings_run_same_scope",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "evaluation_run_id", "company_id"],
            [
                "diagnostic_evaluation_runs.tenant_id",
                "diagnostic_evaluation_runs.id",
                "diagnostic_evaluation_runs.company_id",
            ],
            ondelete="RESTRICT",
            name="fk_diagnostic_findings_run_same_company",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "evaluation_run_id", "branch_id"],
            [
                "diagnostic_evaluation_runs.tenant_id",
                "diagnostic_evaluation_runs.id",
                "diagnostic_evaluation_runs.branch_id",
            ],
            ondelete="RESTRICT",
            name="fk_diagnostic_findings_run_same_branch",
        ),
        ForeignKeyConstraint(
            ["rule_definition_id", "rule_ownership_type"],
            ["diagnostic_rule_definitions.id", "diagnostic_rule_definitions.ownership_type"],
            ondelete="RESTRICT",
            name="fk_diagnostic_findings_rule_ownership",
        ),
        ForeignKeyConstraint(
            ["rule_tenant_id", "rule_definition_id", "rule_ownership_type"],
            [
                "diagnostic_rule_definitions.tenant_id",
                "diagnostic_rule_definitions.id",
                "diagnostic_rule_definitions.ownership_type",
            ],
            ondelete="RESTRICT",
            name="fk_diagnostic_findings_tenant_rule",
        ),
        ForeignKeyConstraint(
            ["rule_definition_id", "rule_version_number"],
            [
                "diagnostic_rule_versions.rule_definition_id",
                "diagnostic_rule_versions.version_number",
            ],
            ondelete="RESTRICT",
            name="fk_diagnostic_findings_rule_version",
        ),
        CheckConstraint(
            f"scope_type IN ({_RULE_SCOPE_SQL})",
            name="ck_diagnostic_findings_scope_type",
        ),
        CheckConstraint(
            _SCOPE_COHERENCE_SQL,
            name="ck_diagnostic_findings_scope",
        ),
        CheckConstraint(
            f"domain IN ({_RULE_DOMAIN_SQL})",
            name="ck_diagnostic_findings_domain",
        ),
        CheckConstraint(
            f"rule_ownership_type IN ({_RULE_OWNERSHIP_SQL})",
            name="ck_diagnostic_findings_rule_ownership_type",
        ),
        CheckConstraint(
            "(rule_ownership_type = 'system' AND rule_tenant_id IS NULL) OR "
            "(rule_ownership_type = 'tenant' AND rule_tenant_id = tenant_id)",
            name="ck_diagnostic_findings_rule_ownership",
        ),
        CheckConstraint(
            f"status IN ({_DIAGNOSTIC_STATUS_SQL})",
            name="ck_diagnostic_findings_status",
        ),
        CheckConstraint(
            f"severity IN ({_SEVERITY_SQL})",
            name="ck_diagnostic_findings_severity",
        ),
        CheckConstraint(
            f"priority IN ({_ACTION_PRIORITY_SQL})",
            name="ck_diagnostic_findings_priority",
        ),
        CheckConstraint(
            "confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1",
            name="ck_diagnostic_findings_confidence",
        ),
        CheckConstraint(
            "affected_to >= affected_from",
            name="ck_diagnostic_findings_affected_period",
        ),
        CheckConstraint(
            "last_observed_at >= first_observed_at",
            name="ck_diagnostic_findings_observation_period",
        ),
        CheckConstraint(
            "occurrence_count >= 1",
            name="ck_diagnostic_findings_occurrence_count",
        ),
        CheckConstraint(
            "analytics_data_version >= 0 AND formula_version >= 1 AND rule_version_number >= 1",
            name="ck_diagnostic_findings_versions",
        ),
        CheckConstraint(
            f"fingerprint ~ '^[0-9a-f]{{{HASH_LENGTH}}}$'",
            name="ck_diagnostic_findings_fingerprint",
        ),
        CheckConstraint(
            "diagnostic_code ~ '^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$'",
            name="ck_diagnostic_findings_code",
        ),
        CheckConstraint(
            "jsonb_typeof(context_snapshot) = 'object'",
            name="ck_diagnostic_findings_context_snapshot",
        ),
        CheckConstraint(
            "(status <> 'acknowledged' OR acknowledged_at IS NOT NULL) AND "
            "(status <> 'resolved' OR resolved_at IS NOT NULL) AND "
            "(status <> 'closed' OR closed_at IS NOT NULL)",
            name="ck_diagnostic_findings_lifecycle",
        ),
        Index(
            "ix_diagnostic_findings_scope_status",
            "tenant_id",
            "company_id",
            "branch_id",
            "status",
            "severity",
        ),
        Index(
            "ix_diagnostic_findings_fingerprint",
            "tenant_id",
            "fingerprint",
            "status",
            "last_observed_at",
        ),
        Index(
            "ix_diagnostic_findings_rule",
            "tenant_id",
            "rule_definition_id",
            "rule_version_number",
            "detected_at",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID | None] = mapped_column()
    branch_id: Mapped[UUID | None] = mapped_column()
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    evaluation_run_id: Mapped[UUID] = mapped_column()
    rule_definition_id: Mapped[UUID] = mapped_column()
    rule_version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_ownership_type: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_tenant_id: Mapped[UUID | None] = mapped_column()
    diagnostic_code: Mapped[str] = mapped_column(String(140), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    affected_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    affected_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    primary_kpi_code: Mapped[str] = mapped_column(String(140), nullable=False)
    observed_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    reference_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    value_unit: Mapped[str | None] = mapped_column(String(40))
    analytics_data_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    formula_version: Mapped[int] = mapped_column(Integer, nullable=False)
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DiagnosticEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable factual evidence supporting one persisted diagnosis."""

    __tablename__ = "diagnostic_evidences"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_diagnostic_evidences_tenant_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "diagnostic_id",
            "id",
            name="uq_diagnostic_evidences_tenant_diagnostic_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "diagnostic_id",
            "evidence_hash",
            name="uq_diagnostic_evidences_hash",
        ),
        UniqueConstraint(
            "tenant_id",
            "diagnostic_id",
            "stable_order",
            name="uq_diagnostic_evidences_order",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "diagnostic_id"],
            ["diagnostic_findings.tenant_id", "diagnostic_findings.id"],
            ondelete="RESTRICT",
            name="fk_diagnostic_evidences_finding_same_tenant",
        ),
        CheckConstraint(
            f"evidence_type IN ({_EVIDENCE_TYPE_SQL})",
            name="ck_diagnostic_evidences_type",
        ),
        CheckConstraint(
            f"direction IN ({_EVIDENCE_DIRECTION_SQL})",
            name="ck_diagnostic_evidences_direction",
        ),
        CheckConstraint(
            f"source_type IN ({_EVIDENCE_SOURCE_SQL})",
            name="ck_diagnostic_evidences_source",
        ),
        CheckConstraint(
            "period_end >= period_start",
            name="ck_diagnostic_evidences_period",
        ),
        CheckConstraint(
            "analytics_data_version >= 0 AND formula_version >= 1",
            name="ck_diagnostic_evidences_versions",
        ),
        CheckConstraint(
            f"evidence_hash ~ '^[0-9a-f]{{{HASH_LENGTH}}}$'",
            name="ck_diagnostic_evidences_hash",
        ),
        CheckConstraint(
            "stable_order >= 0",
            name="ck_diagnostic_evidences_order",
        ),
        CheckConstraint(
            "jsonb_typeof(detail_snapshot) = 'object'",
            name="ck_diagnostic_evidences_detail_snapshot",
        ),
        Index(
            "ix_diagnostic_evidences_finding",
            "tenant_id",
            "diagnostic_id",
            "stable_order",
        ),
        Index(
            "ix_diagnostic_evidences_kpi_period",
            "tenant_id",
            "kpi_code",
            "period_start",
            "period_end",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    diagnostic_id: Mapped[UUID] = mapped_column()
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    kpi_code: Mapped[str] = mapped_column(String(140), nullable=False)
    observed_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    reference_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    unit: Mapped[str | None] = mapped_column(String(40))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dimension_type: Mapped[str | None] = mapped_column(String(80))
    dimension_member_key: Mapped[str | None] = mapped_column(String(300))
    direction: Mapped[str] = mapped_column(String(24), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    analytics_data_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    formula_version: Mapped[int] = mapped_column(Integer, nullable=False)
    detail_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    evidence_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False)
    stable_order: Mapped[int] = mapped_column(Integer, nullable=False)


class DiagnosticHypothesis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Deterministic hypothesis assessment that remains distinct from factual evidence."""

    __tablename__ = "diagnostic_hypotheses"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_diagnostic_hypotheses_tenant_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "diagnostic_id",
            "id",
            name="uq_diagnostic_hypotheses_tenant_diagnostic_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "diagnostic_id",
            "hypothesis_code",
            "logic_version",
            name="uq_diagnostic_hypotheses_definition",
        ),
        UniqueConstraint(
            "tenant_id",
            "diagnostic_id",
            "rank",
            name="uq_diagnostic_hypotheses_rank",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "diagnostic_id"],
            ["diagnostic_findings.tenant_id", "diagnostic_findings.id"],
            ondelete="RESTRICT",
            name="fk_diagnostic_hypotheses_finding_same_tenant",
        ),
        CheckConstraint(
            "hypothesis_code ~ '^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$'",
            name="ck_diagnostic_hypotheses_code",
        ),
        CheckConstraint(
            f"evaluation_status IN ({_HYPOTHESIS_STATUS_SQL})",
            name="ck_diagnostic_hypotheses_status",
        ),
        CheckConstraint(
            "confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1",
            name="ck_diagnostic_hypotheses_confidence",
        ),
        CheckConstraint(
            "rank >= 1",
            name="ck_diagnostic_hypotheses_rank",
        ),
        CheckConstraint(
            "supporting_evidence_count >= 0 AND contradicting_evidence_count >= 0",
            name="ck_diagnostic_hypotheses_evidence_counts",
        ),
        CheckConstraint(
            "jsonb_typeof(definition_snapshot) = 'object'",
            name="ck_diagnostic_hypotheses_definition_snapshot",
        ),
        CheckConstraint(
            "(evaluation_status = 'not_evaluated' AND evaluated_at IS NULL) OR "
            "(evaluation_status <> 'not_evaluated' AND evaluated_at IS NOT NULL)",
            name="ck_diagnostic_hypotheses_evaluation_time",
        ),
        Index(
            "ix_diagnostic_hypotheses_finding",
            "tenant_id",
            "diagnostic_id",
            "evaluation_status",
            "rank",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    diagnostic_id: Mapped[UUID] = mapped_column()
    hypothesis_code: Mapped[str] = mapped_column(String(140), nullable=False)
    definition_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    evaluation_status: Mapped[str] = mapped_column(String(24), nullable=False)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    supporting_evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contradicting_evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    logic_version: Mapped[str] = mapped_column(String(40), nullable=False)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DiagnosticHypothesisEvidence(Base):
    """Tenant-safe factual links that support or contradict one hypothesis."""

    __tablename__ = "diagnostic_hypothesis_evidences"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "diagnostic_id", "hypothesis_id"],
            [
                "diagnostic_hypotheses.tenant_id",
                "diagnostic_hypotheses.diagnostic_id",
                "diagnostic_hypotheses.id",
            ],
            ondelete="RESTRICT",
            name="fk_diagnostic_hypothesis_evidences_hypothesis_same_diagnostic",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "diagnostic_id", "evidence_id"],
            [
                "diagnostic_evidences.tenant_id",
                "diagnostic_evidences.diagnostic_id",
                "diagnostic_evidences.id",
            ],
            ondelete="RESTRICT",
            name="fk_diagnostic_hypothesis_evidences_evidence_same_diagnostic",
        ),
        UniqueConstraint(
            "tenant_id",
            "hypothesis_id",
            "relation",
            "stable_order",
            name="uq_diagnostic_hypothesis_evidences_order",
        ),
        CheckConstraint(
            f"relation IN ({_HYPOTHESIS_EVIDENCE_RELATION_SQL})",
            name="ck_diagnostic_hypothesis_evidences_relation",
        ),
        CheckConstraint(
            "stable_order >= 0",
            name="ck_diagnostic_hypothesis_evidences_order",
        ),
        Index(
            "ix_diagnostic_hypothesis_evidences_evidence",
            "tenant_id",
            "evidence_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    diagnostic_id: Mapped[UUID] = mapped_column()
    hypothesis_id: Mapped[UUID] = mapped_column(primary_key=True)
    evidence_id: Mapped[UUID] = mapped_column(primary_key=True)
    relation: Mapped[str] = mapped_column(String(16), nullable=False)
    stable_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DiagnosticActionRecommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Advisory-only link from a diagnosis to one exact catalog entry."""

    __tablename__ = "diagnostic_action_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_diagnostic_action_recommendations_tenant_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "diagnostic_id",
            "catalog_entry_id",
            name="uq_diagnostic_action_recommendations_entry",
        ),
        UniqueConstraint(
            "tenant_id",
            "diagnostic_id",
            "stable_order",
            name="uq_diagnostic_action_recommendations_order",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "diagnostic_id"],
            ["diagnostic_findings.tenant_id", "diagnostic_findings.id"],
            ondelete="RESTRICT",
            name="fk_diagnostic_action_recommendations_finding_same_tenant",
        ),
        CheckConstraint(
            f"suggested_priority IN ({_ACTION_PRIORITY_SQL})",
            name="ck_diagnostic_action_recommendations_priority",
        ),
        CheckConstraint(
            f"status IN ({_ACTION_RECOMMENDATION_STATUS_SQL})",
            name="ck_diagnostic_action_recommendations_status",
        ),
        CheckConstraint(
            "stable_order >= 0",
            name="ck_diagnostic_action_recommendations_order",
        ),
        CheckConstraint(
            "requires_human_review = true",
            name="ck_diagnostic_action_recommendations_human_review",
        ),
        CheckConstraint(
            "(status = 'reviewed' AND reviewed_at IS NOT NULL) OR status <> 'reviewed'",
            name="ck_diagnostic_action_recommendations_reviewed_at",
        ),
        Index(
            "ix_diagnostic_action_recommendations_finding",
            "tenant_id",
            "diagnostic_id",
            "status",
            "stable_order",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    diagnostic_id: Mapped[UUID] = mapped_column()
    catalog_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("diagnostic_action_catalog_entries.id", ondelete="RESTRICT")
    )
    suggested_priority: Mapped[int] = mapped_column(Integer, nullable=False)
    stable_order: Mapped[int] = mapped_column(Integer, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="suggested")
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DiagnosticSuppression(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    """Auditable cooldown, manual suppression, or configured rule exception."""

    __tablename__ = "diagnostic_suppressions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_diagnostic_suppressions_tenant_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="RESTRICT",
            name="fk_diagnostic_suppressions_company_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="RESTRICT",
            name="fk_diagnostic_suppressions_branch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["rule_definition_id", "rule_ownership_type"],
            ["diagnostic_rule_definitions.id", "diagnostic_rule_definitions.ownership_type"],
            ondelete="RESTRICT",
            name="fk_diagnostic_suppressions_rule_ownership",
        ),
        ForeignKeyConstraint(
            ["rule_tenant_id", "rule_definition_id", "rule_ownership_type"],
            [
                "diagnostic_rule_definitions.tenant_id",
                "diagnostic_rule_definitions.id",
                "diagnostic_rule_definitions.ownership_type",
            ],
            ondelete="RESTRICT",
            name="fk_diagnostic_suppressions_tenant_rule",
        ),
        CheckConstraint(
            f"scope_type IN ({_RULE_SCOPE_SQL})",
            name="ck_diagnostic_suppressions_scope_type",
        ),
        CheckConstraint(
            _SCOPE_COHERENCE_SQL,
            name="ck_diagnostic_suppressions_scope",
        ),
        CheckConstraint(
            f"suppression_type IN ({_SUPPRESSION_TYPE_SQL})",
            name="ck_diagnostic_suppressions_type",
        ),
        CheckConstraint(
            f"target_type IN ({_SUPPRESSION_TARGET_TYPE_SQL})",
            name="ck_diagnostic_suppressions_target_type",
        ),
        CheckConstraint(
            f"reason_code IN ({_SUPPRESSION_REASON_SQL})",
            name="ck_diagnostic_suppressions_reason",
        ),
        CheckConstraint(
            f"source IN ({_SUPPRESSION_SOURCE_SQL})",
            name="ck_diagnostic_suppressions_source",
        ),
        CheckConstraint(
            f"status IN ({_SUPPRESSION_STATUS_SQL})",
            name="ck_diagnostic_suppressions_status",
        ),
        CheckConstraint(
            "(suppression_type = 'cooldown' AND source = 'engine') OR "
            "(suppression_type = 'manual' AND source = 'user') OR "
            "(suppression_type = 'rule_exception' AND source = 'configuration')",
            name="ck_diagnostic_suppressions_type_source",
        ),
        CheckConstraint(
            "(target_type = 'rule' AND rule_definition_id IS NOT NULL AND "
            "rule_ownership_type IS NOT NULL AND diagnostic_fingerprint IS NULL) OR "
            "(target_type = 'fingerprint' AND rule_definition_id IS NULL AND "
            "rule_ownership_type IS NULL AND rule_tenant_id IS NULL AND "
            "diagnostic_fingerprint IS NOT NULL)",
            name="ck_diagnostic_suppressions_target",
        ),
        CheckConstraint(
            "target_type <> 'rule' OR "
            "(rule_ownership_type = 'system' AND rule_tenant_id IS NULL) OR "
            "(rule_ownership_type = 'tenant' AND rule_tenant_id = tenant_id)",
            name="ck_diagnostic_suppressions_rule_ownership",
        ),
        CheckConstraint(
            f"diagnostic_fingerprint IS NULL OR "
            f"diagnostic_fingerprint ~ '^[0-9a-f]{{{HASH_LENGTH}}}$'",
            name="ck_diagnostic_suppressions_fingerprint",
        ),
        CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at",
            name="ck_diagnostic_suppressions_period",
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at >= starts_at",
            name="ck_diagnostic_suppressions_expiration",
        ),
        CheckConstraint(
            "(status <> 'expired' OR expires_at IS NOT NULL) AND "
            "(status <> 'revoked' OR revoked_at IS NOT NULL)",
            name="ck_diagnostic_suppressions_lifecycle",
        ),
        Index(
            "uq_diagnostic_suppressions_target_period",
            "tenant_id",
            "suppression_type",
            "target_type",
            "rule_definition_id",
            "diagnostic_fingerprint",
            "company_id",
            "branch_id",
            "starts_at",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        Index(
            "ix_diagnostic_suppressions_active",
            "tenant_id",
            "company_id",
            "branch_id",
            "status",
            "expires_at",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID | None] = mapped_column()
    branch_id: Mapped[UUID | None] = mapped_column()
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    suppression_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_definition_id: Mapped[UUID | None] = mapped_column()
    rule_ownership_type: Mapped[str | None] = mapped_column(String(16))
    rule_tenant_id: Mapped[UUID | None] = mapped_column()
    diagnostic_fingerprint: Mapped[str | None] = mapped_column(String(HASH_LENGTH))
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audit_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("audit_events.id", ondelete="SET NULL")
    )


class DiagnosticIncident(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    """Tenant-owned deterministic grouping of related persisted diagnoses."""

    __tablename__ = "diagnostic_incidents"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_diagnostic_incidents_tenant_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "incident_code",
            name="uq_diagnostic_incidents_code",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="RESTRICT",
            name="fk_diagnostic_incidents_company_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="RESTRICT",
            name="fk_diagnostic_incidents_branch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "primary_diagnostic_id"],
            ["diagnostic_findings.tenant_id", "diagnostic_findings.id"],
            ondelete="RESTRICT",
            name="fk_diagnostic_incidents_primary_finding_same_tenant",
        ),
        CheckConstraint(
            f"scope_type IN ({_RULE_SCOPE_SQL})",
            name="ck_diagnostic_incidents_scope_type",
        ),
        CheckConstraint(
            _SCOPE_COHERENCE_SQL,
            name="ck_diagnostic_incidents_scope",
        ),
        CheckConstraint(
            f"domain IN ({_RULE_DOMAIN_SQL})",
            name="ck_diagnostic_incidents_domain",
        ),
        CheckConstraint(
            f"aggregate_severity IN ({_SEVERITY_SQL})",
            name="ck_diagnostic_incidents_severity",
        ),
        CheckConstraint(
            f"priority IN ({_ACTION_PRIORITY_SQL})",
            name="ck_diagnostic_incidents_priority",
        ),
        CheckConstraint(
            f"status IN ({_INCIDENT_STATUS_SQL})",
            name="ck_diagnostic_incidents_status",
        ),
        CheckConstraint(
            "incident_code ~ '^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$'",
            name="ck_diagnostic_incidents_code",
        ),
        CheckConstraint(
            f"fingerprint ~ '^[0-9a-f]{{{HASH_LENGTH}}}$'",
            name="ck_diagnostic_incidents_fingerprint",
        ),
        CheckConstraint(
            "last_event_at >= first_event_at",
            name="ck_diagnostic_incidents_period",
        ),
        CheckConstraint(
            "diagnostic_count >= 1",
            name="ck_diagnostic_incidents_count",
        ),
        CheckConstraint(
            "(status <> 'acknowledged' OR acknowledged_at IS NOT NULL) AND "
            "(status <> 'resolved' OR resolved_at IS NOT NULL) AND "
            "(status <> 'closed' OR closed_at IS NOT NULL)",
            name="ck_diagnostic_incidents_lifecycle",
        ),
        Index(
            "ix_diagnostic_incidents_scope_status",
            "tenant_id",
            "company_id",
            "branch_id",
            "status",
            "aggregate_severity",
        ),
        Index(
            "ix_diagnostic_incidents_fingerprint",
            "tenant_id",
            "fingerprint",
            "last_event_at",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID | None] = mapped_column()
    branch_id: Mapped[UUID | None] = mapped_column()
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    incident_code: Mapped[str] = mapped_column(String(140), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    aggregate_severity: Mapped[str] = mapped_column(String(16), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    first_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    diagnostic_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    primary_diagnostic_id: Mapped[UUID] = mapped_column()
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DiagnosticIncidentMembership(Base):
    """Tenant-safe N:N association between incidents and their diagnoses."""

    __tablename__ = "diagnostic_incident_memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "incident_id"],
            ["diagnostic_incidents.tenant_id", "diagnostic_incidents.id"],
            ondelete="CASCADE",
            name="fk_diagnostic_incident_memberships_incident_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "diagnostic_id"],
            ["diagnostic_findings.tenant_id", "diagnostic_findings.id"],
            ondelete="RESTRICT",
            name="fk_diagnostic_incident_memberships_finding_same_tenant",
        ),
        UniqueConstraint(
            "tenant_id",
            "incident_id",
            "stable_order",
            name="uq_diagnostic_incident_memberships_order",
        ),
        CheckConstraint(
            "stable_order >= 0",
            name="ck_diagnostic_incident_memberships_order",
        ),
        Index(
            "ix_diagnostic_incident_memberships_finding",
            "tenant_id",
            "diagnostic_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    incident_id: Mapped[UUID] = mapped_column(primary_key=True)
    diagnostic_id: Mapped[UUID] = mapped_column(primary_key=True)
    stable_order: Mapped[int] = mapped_column(Integer, nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
