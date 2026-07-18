from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConnectorTypeResponse(BaseModel):
    key: str
    name: str
    version: str
    schema_version: str
    capabilities: list[str]
    authentication_types: list[str]
    supported_entities: list[str]
    status: str


class CredentialReferenceCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    company_id: UUID | None = None
    branch_id: UUID | None = None
    provider: Literal["aws-secrets-manager", "vault", "azure-key-vault", "environment"]
    secret_identifier: str = Field(min_length=3, max_length=500)
    display_hint: str = Field(min_length=2, max_length=120)

    @field_validator("secret_identifier")
    @classmethod
    def reject_inline_secret(cls, value: str) -> str:
        allowed_prefixes = (
            "aws-secretsmanager://",
            "vault://",
            "azure-keyvault://",
            "env://",
        )
        if not value.startswith(allowed_prefixes):
            raise ValueError("A secret-manager reference is required; inline secrets are forbidden")
        return value


class CredentialReferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    company_id: UUID | None
    branch_id: UUID | None
    name: str
    provider: str
    display_hint: str
    status: str
    rotated_at: datetime | None
    version: int


class DataSourceCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    connector_key: Literal["deterministic-erp", "file-upload"]
    connector_version: str = Field(default="1.0.0", max_length=40)
    company_id: UUID
    branch_id: UUID | None = None
    credential_reference_id: UUID | None = None
    dataset_type: Literal["all", "product", "supplier", "sale", "purchase", "stock", "price"]
    sync_mode: Literal["full", "incremental"] = "incremental"
    schedule_cron: str | None = Field(default=None, max_length=100)
    configuration: dict[str, Any] = Field(default_factory=dict)


class DataSourceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    status: Literal["active", "inactive"] | None = None
    schedule_cron: str | None = Field(default=None, max_length=100)
    configuration: dict[str, Any] | None = None
    expected_version: int = Field(ge=1)


class DataSourceResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    company_id: UUID
    branch_id: UUID | None
    connector_key: str
    connector_version: str
    name: str
    dataset_type: str
    status: str
    sync_mode: str
    schedule_cron: str | None
    last_sync_at: datetime | None
    next_sync_at: datetime | None
    last_health_status: str | None
    last_health_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class ConnectionTestResponse(BaseModel):
    healthy: bool
    latency_ms: int
    message: str
    checked_at: datetime


class FieldMappingRequest(BaseModel):
    source_field: str = Field(min_length=1, max_length=200)
    target_entity: Literal["product", "supplier", "sale", "purchase", "stock", "price"]
    target_field: str = Field(min_length=1, max_length=120)
    transform_type: Literal[
        "identity",
        "trim",
        "uppercase",
        "lowercase",
        "decimal",
        "integer",
        "date",
        "datetime",
        "boolean",
        "constant",
    ] = "identity"
    transform_config: dict[str, Any] = Field(default_factory=dict)
    required: bool = False
    default_value: str | None = Field(default=None, max_length=500)


class MappingCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    data_source_id: UUID
    dataset_type: Literal["product", "supplier", "sale", "purchase", "stock", "price"]
    connector_version: str = Field(max_length=40)
    source_schema_version: str = Field(max_length=40)
    fields: list[FieldMappingRequest] = Field(min_length=1, max_length=300)
    publish: bool = False


class MappingResponse(BaseModel):
    id: UUID
    version_id: UUID
    data_source_id: UUID
    name: str
    dataset_type: str
    version_number: int
    status: str
    fields: list[FieldMappingRequest]


class SyncStartRequest(BaseModel):
    mode: Literal["full", "incremental"] = "incremental"
    entities: list[Literal["product", "supplier", "sale", "purchase", "stock", "price"]] = Field(
        default_factory=list, max_length=6
    )
    range_start: datetime | None = None
    range_end: datetime | None = None

    @field_validator("range_end")
    @classmethod
    def validate_range_end(cls, value: datetime | None, info: Any) -> datetime | None:
        start = info.data.get("range_start")
        if value is not None and start is not None and value <= start:
            raise ValueError("range_end must be after range_start")
        return value


class ImportBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    company_id: UUID
    branch_id: UUID | None
    data_source_id: UUID
    parent_batch_id: UUID | None
    dataset_type: str
    period_start: date | None
    period_end: date | None
    state: str
    progress_percent: int
    received_records: int
    valid_records: int
    rejected_records: int
    duplicate_records: int
    cancel_requested: bool
    correlation_id: str | None
    queued_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class ProcessingErrorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    batch_id: UUID
    staging_record_id: UUID | None
    step_name: str
    entity_type: str | None
    field_name: str | None
    error_class: str
    error_code: str
    severity: str
    message: str
    retryable: bool
    created_at: datetime


class RejectedRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    batch_id: UUID
    staging_record_id: UUID
    entity_type: str
    reason_code: str
    status: str
    correction_payload: dict[str, Any] | None
    corrected_at: datetime | None
    version: int
    created_at: datetime


class RejectedCorrectionRequest(BaseModel):
    correction_payload: dict[str, Any]
    expected_version: int = Field(ge=1)


class QualityResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    batch_id: UUID
    entity_type: str
    rule_key: str
    severity: str
    evaluated_records: int
    failed_records: int
    score: float
    details: dict[str, Any]
    created_at: datetime


class LineageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    batch_id: UUID
    staging_record_id: UUID | None
    source_entity: str
    source_external_id: str
    source_version: str
    target_entity: str
    target_record_id: str
    operation: str
    created_at: datetime


class RawPayloadResponse(BaseModel):
    file_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    content_sha256: str
    retention_until: date
    download_url: str
