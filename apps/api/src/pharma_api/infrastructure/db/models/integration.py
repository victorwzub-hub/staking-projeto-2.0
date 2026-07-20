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

PROCESSING_STATES = (
    "created",
    "queued",
    "connecting",
    "extracting",
    "received",
    "validating",
    "mapping",
    "normalizing",
    "loading",
    "completed",
    "completed_with_warnings",
    "failed",
    "cancelled",
    "quarantined",
    "retry_scheduled",
)
_STATE_SQL = ",".join(f"'{state}'" for state in PROCESSING_STATES)


class ConnectorDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "connector_definitions"
    __table_args__ = (
        UniqueConstraint("connector_key", "version", name="uq_connector_definitions_key_version"),
        CheckConstraint(
            "status IN ('active','deprecated','disabled')", name="ck_connector_definitions_status"
        ),
    )

    connector_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    authentication_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    supported_entities: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")


class CredentialReference(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "credential_references"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_credential_references_tenant_id"),
        UniqueConstraint("tenant_id", "name", name="uq_credential_references_tenant_name"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_credential_references_company_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_credential_references_branch_same_tenant",
        ),
        CheckConstraint(
            "status IN ('active','rotating','revoked')", name="ck_credential_references_status"
        ),
        Index("ix_credential_references_scope", "tenant_id", "company_id", "branch_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID | None] = mapped_column()
    branch_id: Mapped[UUID | None] = mapped_column()
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    secret_identifier: Mapped[str] = mapped_column(String(500), nullable=False)
    display_hint: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConnectorInstance(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "connector_instances"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_connector_instances_tenant_id"),
        UniqueConstraint("tenant_id", "name", name="uq_connector_instances_tenant_name"),
        ForeignKeyConstraint(
            ["tenant_id", "credential_reference_id"],
            ["credential_references.tenant_id", "credential_references.id"],
            ondelete="RESTRICT",
            name="fk_connector_instances_credential_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_connector_instances_company_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_connector_instances_branch_same_tenant",
        ),
        CheckConstraint(
            "status IN ('draft','active','inactive','error')", name="ck_connector_instances_status"
        ),
        Index("ix_connector_instances_scope", "tenant_id", "company_id", "branch_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column()
    branch_id: Mapped[UUID | None] = mapped_column()
    connector_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("connector_definitions.id", ondelete="RESTRICT")
    )
    credential_reference_id: Mapped[UUID | None] = mapped_column()
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    last_health_status: Mapped[str | None] = mapped_column(String(24))
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DataSource(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "data_sources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_data_sources_tenant_id"),
        UniqueConstraint("tenant_id", "name", name="uq_data_sources_tenant_name"),
        ForeignKeyConstraint(
            ["tenant_id", "connector_instance_id"],
            ["connector_instances.tenant_id", "connector_instances.id"],
            ondelete="CASCADE",
            name="fk_data_sources_instance_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_data_sources_company_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_data_sources_branch_same_tenant",
        ),
        CheckConstraint("status IN ('active','inactive','error')", name="ck_data_sources_status"),
        Index("ix_data_sources_scope_status", "tenant_id", "company_id", "branch_id", "status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column()
    branch_id: Mapped[UUID | None] = mapped_column()
    connector_instance_id: Mapped[UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    dataset_type: Mapped[str] = mapped_column(String(40), nullable=False, default="all")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    sync_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="incremental")
    schedule_cron: Mapped[str | None] = mapped_column(String(100))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MappingProfile(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "mapping_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mapping_profiles_tenant_id"),
        UniqueConstraint(
            "tenant_id", "data_source_id", "name", name="uq_mapping_profiles_source_name"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            ondelete="CASCADE",
            name="fk_mapping_profiles_source_same_tenant",
        ),
        CheckConstraint(
            "status IN ('draft','published','archived')", name="ck_mapping_profiles_status"
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    data_source_id: Mapped[UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    dataset_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")


class MappingVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mapping_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mapping_versions_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "mapping_profile_id",
            "version_number",
            name="uq_mapping_versions_profile_number",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "mapping_profile_id"],
            ["mapping_profiles.tenant_id", "mapping_profiles.id"],
            ondelete="CASCADE",
            name="fk_mapping_versions_profile_same_tenant",
        ),
        CheckConstraint(
            "status IN ('draft','validated','published','retired')",
            name="ck_mapping_versions_status",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    mapping_profile_id: Mapped[UUID] = mapped_column()
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    connector_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class FieldMapping(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "field_mappings"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "mapping_version_id", "source_field", name="uq_field_mappings_source_field"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "mapping_version_id"],
            ["mapping_versions.tenant_id", "mapping_versions.id"],
            ondelete="CASCADE",
            name="fk_field_mappings_version_same_tenant",
        ),
        CheckConstraint(
            "transform_type IN ('identity','trim','uppercase','lowercase','decimal',"
            "'integer','date','datetime','boolean','constant')",
            name="ck_field_mappings_transform",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    mapping_version_id: Mapped[UUID] = mapped_column()
    source_field: Mapped[str] = mapped_column(String(200), nullable=False)
    target_entity: Mapped[str] = mapped_column(String(60), nullable=False)
    target_field: Mapped[str] = mapped_column(String(120), nullable=False)
    transform_type: Mapped[str] = mapped_column(String(24), nullable=False, default="identity")
    transform_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_value: Mapped[str | None] = mapped_column(String(500))


class SyncCursor(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "sync_cursors"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "data_source_id", "cursor_key", name="uq_sync_cursors_source_key"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            ondelete="CASCADE",
            name="fk_sync_cursors_source_same_tenant",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    data_source_id: Mapped[UUID] = mapped_column()
    cursor_key: Mapped[str] = mapped_column(String(120), nullable=False)
    cursor_value: Mapped[str | None] = mapped_column(Text)
    source_version: Mapped[str | None] = mapped_column(String(100))
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ImportBatch(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_import_batches_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "idempotency_key",
            name="uq_import_batches_source_idempotency",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            ondelete="CASCADE",
            name="fk_import_batches_source_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "mapping_version_id"],
            ["mapping_versions.tenant_id", "mapping_versions.id"],
            ondelete="RESTRICT",
            name="fk_import_batches_mapping_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "parent_batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="SET NULL",
            name="fk_import_batches_parent_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_import_batches_company_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_import_batches_branch_same_tenant",
        ),
        CheckConstraint(f"state IN ({_STATE_SQL})", name="ck_import_batches_state"),
        CheckConstraint("progress_percent BETWEEN 0 AND 100", name="ck_import_batches_progress"),
        Index(
            "ix_import_batches_scope_created", "tenant_id", "company_id", "branch_id", "created_at"
        ),
        Index(
            "ix_import_batches_active",
            "tenant_id",
            "state",
            postgresql_where=text(
                "state NOT IN ('completed','completed_with_warnings','cancelled')"
            ),
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column()
    branch_id: Mapped[UUID | None] = mapped_column()
    data_source_id: Mapped[UUID] = mapped_column()
    mapping_version_id: Mapped[UUID | None] = mapped_column()
    parent_batch_id: Mapped[UUID | None] = mapped_column()
    requested_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    dataset_type: Mapped[str] = mapped_column(String(40), nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    state: Mapped[str] = mapped_column(String(40), nullable=False, default="created")
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    received_records: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    valid_records: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    rejected_records: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    duplicate_records: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportedFile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "imported_files"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_imported_files_tenant_id"),
        UniqueConstraint(
            "tenant_id", "data_source_id", "content_sha256", name="uq_imported_files_source_hash"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="CASCADE",
            name="fk_imported_files_batch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            ondelete="CASCADE",
            name="fk_imported_files_source_same_tenant",
        ),
        CheckConstraint("size_bytes >= 0", name="ck_imported_files_size"),
        Index("ix_imported_files_retention", "retention_until"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    batch_id: Mapped[UUID] = mapped_column()
    data_source_id: Mapped[UUID] = mapped_column()
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    object_bucket: Mapped[str] = mapped_column(String(120), nullable=False)
    object_key: Mapped[str] = mapped_column(String(900), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retention_until: Mapped[date] = mapped_column(Date, nullable=False)


class LandingManifest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "landing_manifests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "batch_id", name="uq_landing_manifests_batch"),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="CASCADE",
            name="fk_landing_manifests_batch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "imported_file_id"],
            ["imported_files.tenant_id", "imported_files.id"],
            ondelete="CASCADE",
            name="fk_landing_manifests_file_same_tenant",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    batch_id: Mapped[UUID] = mapped_column()
    imported_file_id: Mapped[UUID] = mapped_column()
    record_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    connector_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class SyncExecution(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "sync_executions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_sync_executions_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "idempotency_key",
            name="uq_sync_executions_source_idempotency",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            ondelete="CASCADE",
            name="fk_sync_executions_source_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="CASCADE",
            name="fk_sync_executions_batch_same_tenant",
        ),
        CheckConstraint(f"state IN ({_STATE_SQL})", name="ck_sync_executions_state"),
        Index("ix_sync_executions_source_created", "tenant_id", "data_source_id", "created_at"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    data_source_id: Mapped[UUID] = mapped_column()
    batch_id: Mapped[UUID] = mapped_column()
    requested_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    request_options: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    state: Mapped[str] = mapped_column(String(40), nullable=False, default="created")
    range_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    range_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SyncAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sync_attempts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "execution_id", "attempt_number", name="uq_sync_attempts_execution_number"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "execution_id"],
            ["sync_executions.tenant_id", "sync_executions.id"],
            ondelete="CASCADE",
            name="fk_sync_attempts_execution_same_tenant",
        ),
        CheckConstraint(f"state IN ({_STATE_SQL})", name="ck_sync_attempts_state"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    execution_id: Mapped[UUID] = mapped_column()
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(40), nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(160))
    error_class: Mapped[str | None] = mapped_column(String(60))
    error_code: Mapped[str | None] = mapped_column(String(100))
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SyncCheckpoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sync_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "execution_id", "step_name", name="uq_sync_checkpoints_execution_step"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "execution_id"],
            ["sync_executions.tenant_id", "sync_executions.id"],
            ondelete="CASCADE",
            name="fk_sync_checkpoints_execution_same_tenant",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    execution_id: Mapped[UUID] = mapped_column()
    step_name: Mapped[str] = mapped_column(String(60), nullable=False)
    cursor_value: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_committed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    source_version: Mapped[str | None] = mapped_column(String(100))


class ProcessingStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "processing_steps"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "batch_id",
            "step_name",
            "attempt_number",
            name="uq_processing_steps_batch_name_attempt",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="CASCADE",
            name="fk_processing_steps_batch_same_tenant",
        ),
        CheckConstraint(f"state IN ({_STATE_SQL})", name="ck_processing_steps_state"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    batch_id: Mapped[UUID] = mapped_column()
    execution_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sync_executions.id", ondelete="CASCADE")
    )
    step_name: Mapped[str] = mapped_column(String(60), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(String(40), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProcessingStatistic(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "processing_statistics"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "batch_id",
            "step_name",
            "entity_type",
            name="uq_processing_statistics_step_entity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="CASCADE",
            name="fk_processing_statistics_batch_same_tenant",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    batch_id: Mapped[UUID] = mapped_column()
    step_name: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    received_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    valid_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bytes_received: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    records_per_second: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))


class StagingRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "staging_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_staging_records_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "batch_id",
            "entity_type",
            "external_id",
            "source_version",
            name="uq_staging_records_batch_identity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="CASCADE",
            name="fk_staging_records_batch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            ondelete="CASCADE",
            name="fk_staging_records_source_same_tenant",
        ),
        CheckConstraint(
            "status IN ('received','valid','rejected','duplicate','loaded')",
            name="ck_staging_records_status",
        ),
        Index("ix_staging_records_batch_status", "tenant_id", "batch_id", "status"),
        Index("ix_staging_records_occurred_brin", "occurred_at", postgresql_using="brin"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    batch_id: Mapped[UUID] = mapped_column()
    data_source_id: Mapped[UUID] = mapped_column()
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    external_id: Mapped[str] = mapped_column(String(240), nullable=False)
    source_version: Mapped[str] = mapped_column(String(100), nullable=False)
    row_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    normalized_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="received")
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProcessingError(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "processing_errors"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="CASCADE",
            name="fk_processing_errors_batch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            ondelete="CASCADE",
            name="fk_processing_errors_staging_same_tenant",
        ),
        CheckConstraint(
            "severity IN ('informational','warning','error','blocking')",
            name="ck_processing_errors_severity",
        ),
        Index("ix_processing_errors_batch_code", "tenant_id", "batch_id", "error_code"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    batch_id: Mapped[UUID] = mapped_column()
    staging_record_id: Mapped[UUID | None] = mapped_column()
    step_name: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(60))
    field_name: Mapped[str | None] = mapped_column(String(160))
    error_class: Mapped[str] = mapped_column(String(60), nullable=False)
    error_code: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    message: Mapped[str] = mapped_column(String(800), nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RejectedRecord(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "rejected_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "staging_record_id", name="uq_rejected_records_staging"),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="CASCADE",
            name="fk_rejected_records_batch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            ondelete="CASCADE",
            name="fk_rejected_records_staging_same_tenant",
        ),
        CheckConstraint(
            "status IN ('open','corrected','ignored','reprocessed')",
            name="ck_rejected_records_status",
        ),
        Index("ix_rejected_records_batch_status", "tenant_id", "batch_id", "status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    batch_id: Mapped[UUID] = mapped_column()
    staging_record_id: Mapped[UUID] = mapped_column()
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    correction_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    corrected_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeadLetter(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "integration_dead_letters"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="CASCADE",
            name="fk_integration_dead_letters_batch_same_tenant",
        ),
        CheckConstraint(
            "status IN ('open','replayed','discarded')", name="ck_integration_dead_letters_status"
        ),
        Index("ix_integration_dead_letters_status", "tenant_id", "status", "created_at"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    batch_id: Mapped[UUID] = mapped_column()
    execution_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sync_executions.id", ondelete="CASCADE")
    )
    step_name: Mapped[str] = mapped_column(String(60), nullable=False)
    error_class: Mapped[str] = mapped_column(String(60), nullable=False)
    reason: Mapped[str] = mapped_column(String(800), nullable=False)
    payload_reference: Mapped[str] = mapped_column(String(900), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")


class QualityRule(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "quality_rules"
    __table_args__ = (
        Index(
            "uq_quality_rules_platform_key",
            "rule_key",
            unique=True,
            postgresql_where=text("tenant_id IS NULL"),
        ),
        Index(
            "uq_quality_rules_tenant_key",
            "tenant_id",
            "rule_key",
            unique=True,
            postgresql_where=text("tenant_id IS NOT NULL"),
        ),
        CheckConstraint(
            "severity IN ('informational','warning','error','blocking')",
            name="ck_quality_rules_severity",
        ),
    )

    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    rule_key: Mapped[str] = mapped_column(String(140), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(60))
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_platform_rule: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class QualityResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "quality_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="CASCADE",
            name="fk_quality_results_batch_same_tenant",
        ),
        Index("ix_quality_results_batch_entity", "tenant_id", "batch_id", "entity_type"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    batch_id: Mapped[UUID] = mapped_column()
    quality_rule_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("quality_rules.id", ondelete="SET NULL")
    )
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    rule_key: Mapped[str] = mapped_column(String(140), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    evaluated_records: Mapped[int] = mapped_column(BigInteger, nullable=False)
    failed_records: Mapped[int] = mapped_column(BigInteger, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class LineageEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "lineage_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="CASCADE",
            name="fk_lineage_events_batch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            ondelete="SET NULL",
            name="fk_lineage_events_staging_same_tenant",
        ),
        Index("ix_lineage_events_target", "tenant_id", "target_entity", "target_record_id"),
        Index("ix_lineage_events_created_brin", "created_at", postgresql_using="brin"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    batch_id: Mapped[UUID] = mapped_column()
    staging_record_id: Mapped[UUID | None] = mapped_column()
    source_entity: Mapped[str] = mapped_column(String(60), nullable=False)
    source_external_id: Mapped[str] = mapped_column(String(240), nullable=False)
    source_version: Mapped[str] = mapped_column(String(100), nullable=False)
    target_entity: Mapped[str] = mapped_column(String(60), nullable=False)
    target_record_id: Mapped[str] = mapped_column(String(240), nullable=False)
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StateTransition(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "processing_state_transitions"
    __table_args__ = (
        Index(
            "ix_processing_state_transitions_resource",
            "tenant_id",
            "resource_type",
            "resource_id",
            "created_at",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(nullable=False)
    from_state: Mapped[str] = mapped_column(String(40), nullable=False)
    to_state: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(160))
    reason: Mapped[str | None] = mapped_column(String(500))
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutboxEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "integration_outbox_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_integration_outbox_idempotency"),
        Index(
            "ix_integration_outbox_pending",
            "created_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    aggregate_type: Mapped[str] = mapped_column(String(60), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class InboxMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "integration_inbox_messages"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "external_message_id",
            name="uq_integration_inbox_external",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            ondelete="CASCADE",
            name="fk_integration_inbox_source_same_tenant",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    data_source_id: Mapped[UUID] = mapped_column()
    external_message_id: Mapped[str] = mapped_column(String(240), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="received")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookReceipt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "webhook_receipts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "data_source_id", "external_event_id", name="uq_webhook_receipts_external"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            ondelete="CASCADE",
            name="fk_webhook_receipts_source_same_tenant",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    data_source_id: Mapped[UUID] = mapped_column()
    external_event_id: Mapped[str] = mapped_column(String(240), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(String(900), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="received")


class ProcessingLease(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "processing_leases"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "resource_type", "resource_id", name="uq_processing_leases_resource"
        ),
        Index("ix_processing_leases_expiry", "lease_until"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(nullable=False)
    owner_id: Mapped[str] = mapped_column(String(180), nullable=False)
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
