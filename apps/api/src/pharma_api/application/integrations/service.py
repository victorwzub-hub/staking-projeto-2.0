from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.audit.service import AuditRecord, append_audit_event
from pharma_api.application.auth.types import AuthContext, AuthorizationTarget
from pharma_api.application.integrations.connectors import ConnectionTestResult, connector_registry
from pharma_api.core.errors import AppError
from pharma_api.domain.integrations.state_machine import ProcessingState, assert_transition
from pharma_api.infrastructure.db.models.integration import (
    ConnectorDefinition,
    ConnectorInstance,
    CredentialReference,
    DataSource,
    FieldMapping,
    ImportBatch,
    LandingManifest,
    MappingProfile,
    MappingVersion,
    OutboxEvent,
    RejectedRecord,
    StagingRecord,
    StateTransition,
    SyncExecution,
)
from pharma_api.schemas.integrations import (
    DataSourceCreateRequest,
    DataSourceResponse,
    DataSourceUpdateRequest,
    FieldMappingRequest,
    MappingCreateRequest,
    MappingResponse,
    SyncStartRequest,
)

_SENSITIVE_CONFIGURATION_PARTS = (
    "password",
    "secret",
    "token",
    "authorization",
    "credential",
    "private_key",
)
_TARGET_FIELDS: dict[str, frozenset[str]] = {
    "product": frozenset(
        {
            "sku",
            "name",
            "ean",
            "brand",
            "manufacturer",
            "category",
            "unit",
            "presentation",
            "commercial_status",
        }
    ),
    "supplier": frozenset(
        {"supplier_code", "name", "tax_id_hash", "lead_time_days", "minimum_order"}
    ),
    "sale": frozenset(
        {
            "sale_number",
            "occurred_at",
            "channel",
            "customer_key",
            "gross_total",
            "discount_total",
            "net_total",
            "items",
            "payments",
        }
    ),
    "purchase": frozenset(
        {
            "purchase_number",
            "supplier_code",
            "occurred_at",
            "status",
            "freight_total",
            "tax_total",
            "items",
        }
    ),
    "stock": frozenset(
        {
            "product_code",
            "occurred_at",
            "on_hand",
            "reserved",
            "in_transit",
            "movement_type",
            "movement_quantity",
            "lot_number",
            "expires_on",
        }
    ),
    "price": frozenset(
        {
            "product_code",
            "price",
            "reference_price",
            "reference_cost",
            "valid_from",
            "valid_to",
            "promotion",
            "discount_type",
            "discount_value",
        }
    ),
}


def sanitize_connector_configuration(configuration: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(configuration, ensure_ascii=False, default=str)
    if len(encoded.encode()) > 32_768:
        raise AppError(
            code="configuration_too_large",
            message="Connector configuration exceeds 32 KiB",
            status_code=413,
        )

    def walk(value: Any, path: str = "") -> Any:
        if isinstance(value, dict):
            clean: dict[str, Any] = {}
            for key, item in value.items():
                normalized = str(key).casefold()
                if any(part in normalized for part in _SENSITIVE_CONFIGURATION_PARTS):
                    raise AppError(
                        code="inline_secret_forbidden",
                        message="Secrets must be stored through a credential reference",
                        details={"field": f"{path}.{key}".strip(".")},
                    )
                clean[str(key)] = walk(item, f"{path}.{key}")
            return clean
        if isinstance(value, list):
            return [walk(item, path) for item in value[:100]]
        if value is None or isinstance(value, str | int | float | bool):
            return value
        raise AppError(code="invalid_configuration", message="Unsupported configuration value")

    return cast(dict[str, Any], walk(configuration))


def require_scope_access(
    auth: AuthContext,
    permission_key: str,
    *,
    company_id: UUID,
    branch_id: UUID | None,
) -> AuthorizationTarget:
    if auth.tenant_id is None:
        raise AppError(
            code="tenant_context_required", message="Select a tenant first", status_code=409
        )
    target = AuthorizationTarget(auth.tenant_id, company_id, branch_id)
    if not auth.can_access(permission_key, target):
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    return target


async def create_credential_reference(
    session: AsyncSession,
    *,
    auth: AuthContext,
    name: str,
    company_id: UUID | None,
    branch_id: UUID | None,
    provider: str,
    secret_identifier: str,
    display_hint: str,
    correlation_id: str | None,
) -> CredentialReference:
    if auth.tenant_id is None:
        raise AppError(
            code="tenant_context_required", message="Select a tenant first", status_code=409
        )
    if company_id is not None:
        require_scope_access(
            auth,
            "integration.create",
            company_id=company_id,
            branch_id=branch_id,
        )
    elif not auth.has_tenant_wide_permission("integration.create", auth.tenant_id):
        raise AppError(code="forbidden", message="Tenant-wide permission required", status_code=403)
    reference = CredentialReference(
        tenant_id=auth.tenant_id,
        company_id=company_id,
        branch_id=branch_id,
        name=name.strip(),
        provider=provider,
        secret_identifier=secret_identifier,
        display_hint=display_hint.strip(),
        status="active",
    )
    session.add(reference)
    await session.flush()
    await append_audit_event(
        session,
        AuditRecord(
            action="integration.credential_reference.created",
            category="integration_security",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=auth.tenant_id,
            company_id=company_id,
            branch_id=branch_id,
            resource_type="credential_reference",
            resource_id=str(reference.id),
            correlation_id=correlation_id,
            metadata={"provider": provider, "display_hint": display_hint},
        ),
    )
    return reference


async def create_data_source(
    session: AsyncSession,
    *,
    auth: AuthContext,
    payload: DataSourceCreateRequest,
    correlation_id: str | None,
) -> DataSource:
    target = require_scope_access(
        auth,
        "integration.create",
        company_id=payload.company_id,
        branch_id=payload.branch_id,
    )
    definition = await session.scalar(
        select(ConnectorDefinition).where(
            ConnectorDefinition.connector_key == payload.connector_key,
            ConnectorDefinition.version == payload.connector_version,
            ConnectorDefinition.status == "active",
        )
    )
    if definition is None:
        raise AppError(
            code="connector_not_found", message="Connector version not found", status_code=404
        )
    if payload.credential_reference_id is not None:
        reference = await session.scalar(
            select(CredentialReference).where(
                CredentialReference.id == payload.credential_reference_id,
                CredentialReference.tenant_id == target.tenant_id,
                CredentialReference.status == "active",
            )
        )
        if reference is None:
            raise AppError(
                code="credential_not_found",
                message="Credential reference not found",
                status_code=404,
            )
    configuration = sanitize_connector_configuration(payload.configuration)
    instance = ConnectorInstance(
        tenant_id=target.tenant_id,
        company_id=payload.company_id,
        branch_id=payload.branch_id,
        connector_definition_id=definition.id,
        credential_reference_id=payload.credential_reference_id,
        name=f"{payload.name.strip()} connector",
        status="active",
        configuration=configuration,
    )
    session.add(instance)
    await session.flush()
    source = DataSource(
        tenant_id=target.tenant_id,
        company_id=payload.company_id,
        branch_id=payload.branch_id,
        connector_instance_id=instance.id,
        name=payload.name.strip(),
        dataset_type=payload.dataset_type,
        status="active",
        sync_mode=payload.sync_mode,
        schedule_cron=payload.schedule_cron,
    )
    session.add(source)
    await session.flush()
    await append_audit_event(
        session,
        AuditRecord(
            action="integration.source.created",
            category="integration",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=target.tenant_id,
            company_id=payload.company_id,
            branch_id=payload.branch_id,
            resource_type="data_source",
            resource_id=str(source.id),
            correlation_id=correlation_id,
            metadata={"connector": payload.connector_key, "dataset_type": payload.dataset_type},
        ),
    )
    return source


async def source_response(session: AsyncSession, source: DataSource) -> DataSourceResponse:
    instance = await session.get(ConnectorInstance, source.connector_instance_id)
    if instance is None:
        raise RuntimeError("Connector instance invariant violated")
    definition = await session.get(ConnectorDefinition, instance.connector_definition_id)
    if definition is None:
        raise RuntimeError("Connector definition invariant violated")
    return DataSourceResponse(
        id=source.id,
        tenant_id=source.tenant_id,
        company_id=source.company_id,
        branch_id=source.branch_id,
        connector_key=definition.connector_key,
        connector_version=definition.version,
        name=source.name,
        dataset_type=source.dataset_type,
        status=source.status,
        sync_mode=source.sync_mode,
        schedule_cron=source.schedule_cron,
        last_sync_at=source.last_sync_at,
        next_sync_at=source.next_sync_at,
        last_health_status=instance.last_health_status,
        last_health_at=instance.last_health_at,
        version=source.version,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


async def update_data_source(
    session: AsyncSession,
    *,
    source: DataSource,
    auth: AuthContext,
    payload: DataSourceUpdateRequest,
    correlation_id: str | None,
) -> DataSource:
    require_scope_access(
        auth,
        "integration.edit",
        company_id=source.company_id,
        branch_id=source.branch_id,
    )
    if source.version != payload.expected_version:
        raise AppError(code="version_conflict", message="Resource was modified", status_code=409)
    if payload.name is not None:
        source.name = payload.name.strip()
    if payload.status is not None:
        source.status = payload.status
    if payload.schedule_cron is not None:
        source.schedule_cron = payload.schedule_cron
    if payload.configuration is not None:
        instance = await session.get(ConnectorInstance, source.connector_instance_id)
        if instance is None:
            raise RuntimeError("Connector instance invariant violated")
        instance.configuration = sanitize_connector_configuration(payload.configuration)
        instance.version += 1
    source.version += 1
    await append_audit_event(
        session,
        AuditRecord(
            action="integration.source.updated",
            category="integration",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=source.tenant_id,
            company_id=source.company_id,
            branch_id=source.branch_id,
            resource_type="data_source",
            resource_id=str(source.id),
            correlation_id=correlation_id,
        ),
    )
    return source


async def test_data_source_connection(
    session: AsyncSession, source: DataSource
) -> ConnectionTestResult:
    instance = await session.get(ConnectorInstance, source.connector_instance_id)
    if instance is None:
        raise RuntimeError("Connector instance invariant violated")
    definition = await session.get(ConnectorDefinition, instance.connector_definition_id)
    if definition is None:
        raise RuntimeError("Connector definition invariant violated")
    connector = connector_registry.get(definition.connector_key)
    try:
        result = await asyncio.to_thread(connector.test_connection, instance.configuration)
    except Exception:
        instance.last_health_status = "unhealthy"
        instance.last_health_at = datetime.now(UTC)
        raise
    instance.last_health_status = "healthy" if result.healthy else "unhealthy"
    instance.last_health_at = result.checked_at
    return result


def validate_mapping_fields(fields: list[FieldMappingRequest], dataset_type: str) -> None:
    seen_sources: set[str] = set()
    for field in fields:
        if field.source_field in seen_sources:
            raise AppError(code="duplicate_source_field", message="Source fields must be unique")
        seen_sources.add(field.source_field)
        if field.target_entity != dataset_type:
            raise AppError(code="mapping_entity_mismatch", message="Mapping target entity mismatch")
        if field.target_field not in _TARGET_FIELDS[dataset_type]:
            raise AppError(
                code="unknown_target_field",
                message="Mapping target field is not supported",
                details={"field": field.target_field},
            )


async def create_mapping(
    session: AsyncSession,
    *,
    auth: AuthContext,
    payload: MappingCreateRequest,
) -> MappingResponse:
    source = await session.get(DataSource, payload.data_source_id)
    if source is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    require_scope_access(
        auth,
        "integration.mapping",
        company_id=source.company_id,
        branch_id=source.branch_id,
    )
    validate_mapping_fields(payload.fields, payload.dataset_type)
    profile = MappingProfile(
        tenant_id=source.tenant_id,
        data_source_id=source.id,
        name=payload.name.strip(),
        dataset_type=payload.dataset_type,
        status="published" if payload.publish else "draft",
    )
    session.add(profile)
    await session.flush()
    version = MappingVersion(
        tenant_id=source.tenant_id,
        mapping_profile_id=profile.id,
        version_number=1,
        connector_version=payload.connector_version,
        source_schema_version=payload.source_schema_version,
        status="published" if payload.publish else "validated",
        published_at=datetime.now(UTC) if payload.publish else None,
        published_by_user_id=auth.user.id if payload.publish else None,
    )
    session.add(version)
    await session.flush()
    for field in payload.fields:
        session.add(
            FieldMapping(
                tenant_id=source.tenant_id,
                mapping_version_id=version.id,
                **field.model_dump(),
            )
        )
    await session.flush()
    return MappingResponse(
        id=profile.id,
        version_id=version.id,
        data_source_id=source.id,
        name=profile.name,
        dataset_type=profile.dataset_type,
        version_number=version.version_number,
        status=version.status,
        fields=payload.fields,
    )


async def transition_batch(
    session: AsyncSession,
    batch: ImportBatch,
    target: ProcessingState,
    *,
    actor_type: str,
    actor_id: str | None,
    reason: str | None = None,
) -> None:
    current = ProcessingState(batch.state)
    assert_transition(current, target)
    if current == target:
        return
    batch.state = target.value
    batch.version += 1
    now = datetime.now(UTC)
    if target is ProcessingState.QUEUED:
        batch.queued_at = now
    if (
        target in {ProcessingState.CONNECTING, ProcessingState.RECEIVED}
        and batch.started_at is None
    ):
        batch.started_at = now
    if target in {
        ProcessingState.COMPLETED,
        ProcessingState.COMPLETED_WITH_WARNINGS,
        ProcessingState.CANCELLED,
    }:
        batch.completed_at = now
        batch.progress_percent = 100
    session.add(
        StateTransition(
            tenant_id=batch.tenant_id,
            resource_type="import_batch",
            resource_id=batch.id,
            from_state=current.value,
            to_state=target.value,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            correlation_id=batch.correlation_id,
            created_at=now,
        )
    )
    execution = await session.scalar(
        select(SyncExecution).where(SyncExecution.batch_id == batch.id).with_for_update()
    )
    if execution is not None:
        assert_transition(execution.state, target)
        execution.state = target.value
        execution.version += 1
        if target in {ProcessingState.CONNECTING, ProcessingState.RECEIVED}:
            execution.started_at = execution.started_at or now
        if batch.completed_at is not None:
            execution.completed_at = batch.completed_at


async def start_sync(
    session: AsyncSession,
    *,
    auth: AuthContext,
    source: DataSource,
    request: SyncStartRequest,
    idempotency_key: str,
    correlation_id: str | None,
) -> tuple[ImportBatch, bool]:
    require_scope_access(
        auth,
        "integration.sync",
        company_id=source.company_id,
        branch_id=source.branch_id,
    )
    if source.status != "active":
        raise AppError(code="source_inactive", message="Data source is inactive", status_code=409)
    existing = await session.scalar(
        select(ImportBatch).where(
            ImportBatch.tenant_id == source.tenant_id,
            ImportBatch.data_source_id == source.id,
            ImportBatch.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return existing, False
    instance = await session.get(ConnectorInstance, source.connector_instance_id)
    if instance is None:
        raise RuntimeError("Connector instance invariant violated")
    definition = await session.get(ConnectorDefinition, instance.connector_definition_id)
    if definition is None:
        raise RuntimeError("Connector definition invariant violated")
    if definition.connector_key == "file-upload":
        raise AppError(
            code="upload_required",
            message="File sources must be started by uploading a file",
            status_code=409,
        )
    latest_mapping = await session.scalar(
        select(MappingVersion)
        .join(MappingProfile, MappingProfile.id == MappingVersion.mapping_profile_id)
        .where(
            MappingProfile.data_source_id == source.id,
            MappingVersion.status == "published",
        )
        .order_by(MappingVersion.version_number.desc())
    )
    batch = ImportBatch(
        tenant_id=source.tenant_id,
        company_id=source.company_id,
        branch_id=source.branch_id,
        data_source_id=source.id,
        mapping_version_id=latest_mapping.id if latest_mapping else None,
        requested_by_user_id=auth.user.id,
        idempotency_key=idempotency_key,
        dataset_type=source.dataset_type,
        state=ProcessingState.CREATED.value,
        correlation_id=correlation_id,
    )
    session.add(batch)
    await session.flush()
    execution = SyncExecution(
        tenant_id=source.tenant_id,
        data_source_id=source.id,
        batch_id=batch.id,
        requested_by_user_id=auth.user.id,
        idempotency_key=idempotency_key,
        mode=request.mode,
        request_options={
            "entities": request.entities,
            "range_start": request.range_start.isoformat() if request.range_start else None,
            "range_end": request.range_end.isoformat() if request.range_end else None,
        },
        state=ProcessingState.CREATED.value,
        range_start=request.range_start,
        range_end=request.range_end,
    )
    session.add(execution)
    await session.flush()
    await transition_batch(
        session,
        batch,
        ProcessingState.QUEUED,
        actor_type="user",
        actor_id=str(auth.user.id),
    )
    session.add(
        OutboxEvent(
            tenant_id=source.tenant_id,
            aggregate_type="import_batch",
            aggregate_id=batch.id,
            event_type="integration.sync.requested",
            idempotency_key=f"sync-requested:{batch.id}",
            payload={"batch_id": str(batch.id), "source_id": str(source.id)},
        )
    )
    await session.flush()
    await session.refresh(batch)
    await session.commit()
    from pharma_api.infrastructure.integrations.tasks import acquire_batch

    acquire_batch.send(str(batch.id), str(batch.tenant_id), correlation_id or "")
    return batch, True


async def cancel_batch(
    session: AsyncSession,
    *,
    auth: AuthContext,
    batch: ImportBatch,
    correlation_id: str | None,
) -> ImportBatch:
    require_scope_access(
        auth,
        "integration.cancel",
        company_id=batch.company_id,
        branch_id=batch.branch_id,
    )
    batch.cancel_requested = True
    if batch.state in {ProcessingState.CREATED.value, ProcessingState.QUEUED.value}:
        await transition_batch(
            session,
            batch,
            ProcessingState.CANCELLED,
            actor_type="user",
            actor_id=str(auth.user.id),
            reason="cooperative cancellation requested",
        )
    await append_audit_event(
        session,
        AuditRecord(
            action="integration.batch.cancelled",
            category="integration",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=batch.tenant_id,
            company_id=batch.company_id,
            branch_id=batch.branch_id,
            resource_type="import_batch",
            resource_id=str(batch.id),
            correlation_id=correlation_id,
        ),
    )
    await session.flush()
    await session.refresh(batch)
    return batch


async def reprocess_batch(
    session: AsyncSession,
    *,
    auth: AuthContext,
    parent: ImportBatch,
    idempotency_key: str,
    correlation_id: str | None,
) -> tuple[ImportBatch, bool]:
    require_scope_access(
        auth,
        "integration.reprocess",
        company_id=parent.company_id,
        branch_id=parent.branch_id,
    )
    existing = await session.scalar(
        select(ImportBatch).where(
            ImportBatch.tenant_id == parent.tenant_id,
            ImportBatch.data_source_id == parent.data_source_id,
            ImportBatch.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return existing, False
    manifest = await session.scalar(
        select(LandingManifest).where(LandingManifest.batch_id == parent.id)
    )
    if manifest is None:
        raise AppError(
            code="landing_not_found", message="No landing payload to replay", status_code=409
        )
    replay = ImportBatch(
        tenant_id=parent.tenant_id,
        company_id=parent.company_id,
        branch_id=parent.branch_id,
        data_source_id=parent.data_source_id,
        mapping_version_id=parent.mapping_version_id,
        parent_batch_id=parent.id,
        requested_by_user_id=auth.user.id,
        idempotency_key=idempotency_key,
        content_hash=parent.content_hash,
        dataset_type=parent.dataset_type,
        period_start=parent.period_start,
        period_end=parent.period_end,
        state=ProcessingState.CREATED.value,
        correlation_id=correlation_id,
    )
    session.add(replay)
    await session.flush()
    session.add(
        LandingManifest(
            tenant_id=parent.tenant_id,
            batch_id=replay.id,
            imported_file_id=manifest.imported_file_id,
            record_count=manifest.record_count,
            payload_sha256=manifest.payload_sha256,
            connector_version=manifest.connector_version,
            source_schema_version=manifest.source_schema_version,
            metadata_json={**manifest.metadata_json, "replayed_from": str(parent.id)},
        )
    )
    await transition_batch(
        session,
        replay,
        ProcessingState.QUEUED,
        actor_type="user",
        actor_id=str(auth.user.id),
    )
    await session.flush()
    await session.refresh(replay)
    await session.commit()
    from pharma_api.infrastructure.integrations.tasks import parse_batch

    parse_batch.send(str(replay.id), str(replay.tenant_id), correlation_id or "")
    return replay, True


async def correct_rejected_record(
    session: AsyncSession,
    *,
    auth: AuthContext,
    rejected: RejectedRecord,
    correction: dict[str, Any],
    expected_version: int,
) -> RejectedRecord:
    if rejected.version != expected_version:
        raise AppError(code="version_conflict", message="Resource was modified", status_code=409)
    batch = await session.get(ImportBatch, rejected.batch_id)
    if batch is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    require_scope_access(
        auth,
        "integration.correct",
        company_id=batch.company_id,
        branch_id=batch.branch_id,
    )
    if len(json.dumps(correction, default=str).encode()) > 65_536:
        raise AppError(
            code="correction_too_large", message="Correction exceeds 64 KiB", status_code=413
        )
    record = await session.get(StagingRecord, rejected.staging_record_id)
    if record is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    rejected.correction_payload = correction
    rejected.corrected_by_user_id = auth.user.id
    rejected.corrected_at = datetime.now(UTC)
    rejected.status = "corrected"
    rejected.version += 1
    record.raw_payload = correction
    record.normalized_payload = None
    record.status = "received"
    record.error_count = 0
    return rejected


async def next_mapping_version_number(
    session: AsyncSession, profile_id: UUID, tenant_id: UUID
) -> int:
    current = await session.scalar(
        select(func.max(MappingVersion.version_number)).where(
            MappingVersion.mapping_profile_id == profile_id,
            MappingVersion.tenant_id == tenant_id,
        )
    )
    return int(current or 0) + 1
