from __future__ import annotations

import base64
import csv
import io
import json
import re
import tempfile
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from pharma_api.api.dependencies import (
    CSRFProtectedAuth,
    DBSession,
    require_permission,
)
from pharma_api.application.audit.service import AuditRecord, append_audit_event
from pharma_api.application.auth.scope_filters import (
    integration_batch_visibility_filter,
    integration_source_visibility_filter,
)
from pharma_api.application.auth.types import AuthContext
from pharma_api.application.integrations.service import (
    cancel_batch,
    correct_rejected_record,
    create_credential_reference,
    create_data_source,
    create_mapping,
    reprocess_batch,
    require_scope_access,
    source_response,
    start_sync,
    test_data_source_connection,
    transition_batch,
    update_data_source,
    validate_mapping_fields,
)
from pharma_api.core.config import get_settings
from pharma_api.core.errors import AppError
from pharma_api.domain.integrations.state_machine import ProcessingState
from pharma_api.infrastructure.db.models.canonical import (
    Product,
    ProductPrice,
    PurchaseOrder,
    Sale,
    StockBalance,
    Supplier,
)
from pharma_api.infrastructure.db.models.integration import (
    ConnectorDefinition,
    ConnectorInstance,
    CredentialReference,
    DataSource,
    DeadLetter,
    FieldMapping,
    ImportBatch,
    ImportedFile,
    LandingManifest,
    LineageEvent,
    MappingProfile,
    MappingVersion,
    ProcessingError,
    ProcessingStatistic,
    QualityResult,
    RejectedRecord,
)
from pharma_api.infrastructure.object_storage import get_object_storage
from pharma_api.schemas.common import CursorPage, MessageResponse, Page
from pharma_api.schemas.integrations import (
    ConnectionTestResponse,
    ConnectorTypeResponse,
    CredentialReferenceCreateRequest,
    CredentialReferenceResponse,
    DataSourceCreateRequest,
    DataSourceResponse,
    DataSourceUpdateRequest,
    ImportBatchResponse,
    LineageResponse,
    MappingCreateRequest,
    MappingResponse,
    ProcessingErrorResponse,
    QualityResultResponse,
    RawPayloadResponse,
    RejectedCorrectionRequest,
    RejectedRecordResponse,
    SyncStartRequest,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])
Reader = Annotated[AuthContext, Depends(require_permission("integration.view"))]
ErrorReader = Annotated[AuthContext, Depends(require_permission("integration.errors"))]
QualityReader = Annotated[AuthContext, Depends(require_permission("integration.quality"))]
RawReader = Annotated[AuthContext, Depends(require_permission("integration.raw"))]
Exporter = Annotated[AuthContext, Depends(require_permission("integration.export"))]

_ALLOWED_EXTENSIONS = {".csv", ".json", ".jsonl", ".ndjson"}
_ALLOWED_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/json",
    "application/x-ndjson",
    "text/plain",
}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@router.get("/observability", response_model=dict[str, int | float | None])
async def integration_observability(
    session: DBSession, auth: QualityReader
) -> dict[str, int | float | None]:
    visible = integration_batch_visibility_filter(auth, "integration.quality")
    visible_batches = select(ImportBatch.id).where(visible)
    state_rows = (
        await session.execute(
            select(ImportBatch.state, func.count(ImportBatch.id))
            .where(visible)
            .group_by(ImportBatch.state)
        )
    ).all()
    states = {state: int(count) for state, count in state_rows}
    totals = (
        await session.execute(
            select(
                func.coalesce(func.sum(ImportBatch.received_records), 0),
                func.coalesce(func.sum(ImportBatch.valid_records), 0),
                func.coalesce(func.sum(ImportBatch.rejected_records), 0),
                func.coalesce(func.sum(ImportBatch.duplicate_records), 0),
            ).where(visible)
        )
    ).one()
    storage_bytes = int(
        await session.scalar(
            select(func.coalesce(func.sum(ImportedFile.size_bytes), 0)).where(
                ImportedFile.batch_id.in_(visible_batches)
            )
        )
        or 0
    )
    dead_letters = int(
        await session.scalar(
            select(func.count(DeadLetter.id)).where(DeadLetter.batch_id.in_(visible_batches))
        )
        or 0
    )
    average_rps = await session.scalar(
        select(func.avg(ProcessingStatistic.records_per_second)).where(
            ProcessingStatistic.batch_id.in_(visible_batches),
            ProcessingStatistic.records_per_second.is_not(None),
        )
    )
    average_quality = await session.scalar(
        select(func.avg(QualityResult.score)).where(
            QualityResult.batch_id.in_(visible_batches),
            QualityResult.rule_key == "platform.overall",
        )
    )
    terminal = {"completed", "completed_with_warnings", "failed", "cancelled"}
    return {
        "syncs_started": sum(states.values()),
        "syncs_completed": states.get("completed", 0) + states.get("completed_with_warnings", 0),
        "syncs_failed": states.get("failed", 0),
        "backlog": sum(count for state, count in states.items() if state not in terminal),
        "dead_letters": dead_letters,
        "records_received": int(totals[0]),
        "records_valid": int(totals[1]),
        "records_rejected": int(totals[2]),
        "records_duplicate": int(totals[3]),
        "storage_bytes": storage_bytes,
        "average_records_per_second": float(average_rps) if average_rps is not None else None,
        "average_quality_score": float(average_quality) if average_quality is not None else None,
    }


def _correlation_id(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


async def _source_or_404(
    session: DBSession, auth: AuthContext, source_id: UUID, permission: str = "integration.view"
) -> DataSource:
    source = await session.scalar(
        select(DataSource).where(
            DataSource.id == source_id,
            integration_source_visibility_filter(auth, permission),
        )
    )
    if source is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    return source


async def _batch_or_404(
    session: DBSession, auth: AuthContext, batch_id: UUID, permission: str = "integration.view"
) -> ImportBatch:
    batch = await session.scalar(
        select(ImportBatch).where(
            ImportBatch.id == batch_id,
            integration_batch_visibility_filter(auth, permission),
        )
    )
    if batch is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    return batch


@router.get("/connectors", response_model=list[ConnectorTypeResponse])
async def list_connectors(session: DBSession, auth: Reader) -> list[ConnectorTypeResponse]:
    del auth
    definitions = list(
        (
            await session.scalars(
                select(ConnectorDefinition)
                .where(ConnectorDefinition.status != "disabled")
                .order_by(ConnectorDefinition.connector_key, ConnectorDefinition.version)
            )
        ).all()
    )
    return [
        ConnectorTypeResponse(
            key=item.connector_key,
            name=item.name,
            version=item.version,
            schema_version=item.schema_version,
            capabilities=item.capabilities,
            authentication_types=item.authentication_types,
            supported_entities=item.supported_entities,
            status=item.status,
        )
        for item in definitions
    ]


@router.get("/credential-references", response_model=list[CredentialReferenceResponse])
async def list_credential_references(
    session: DBSession, auth: Reader
) -> list[CredentialReferenceResponse]:
    if auth.tenant_id is None:
        return []
    references = list(
        (
            await session.scalars(
                select(CredentialReference)
                .where(CredentialReference.tenant_id == auth.tenant_id)
                .order_by(CredentialReference.name)
            )
        ).all()
    )
    return [CredentialReferenceResponse.model_validate(item) for item in references]


@router.post(
    "/credential-references",
    response_model=CredentialReferenceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_credential_reference(
    payload: CredentialReferenceCreateRequest,
    request: Request,
    session: DBSession,
    auth: CSRFProtectedAuth,
) -> CredentialReferenceResponse:
    reference = await create_credential_reference(
        session,
        auth=auth,
        correlation_id=_correlation_id(request),
        **payload.model_dump(),
    )
    return CredentialReferenceResponse.model_validate(reference)


@router.get("/sources", response_model=Page[DataSourceResponse])
async def list_sources(
    session: DBSession,
    auth: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[DataSourceResponse]:
    visible = integration_source_visibility_filter(auth, "integration.view")
    total = int(
        await session.scalar(select(func.count()).select_from(DataSource).where(visible)) or 0
    )
    sources = list(
        (
            await session.scalars(
                select(DataSource)
                .where(visible)
                .order_by(DataSource.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    return Page(
        items=[await source_response(session, source) for source in sources],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/sources", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED)
async def add_source(
    payload: DataSourceCreateRequest,
    request: Request,
    session: DBSession,
    auth: CSRFProtectedAuth,
) -> DataSourceResponse:
    source = await create_data_source(
        session, auth=auth, payload=payload, correlation_id=_correlation_id(request)
    )
    return await source_response(session, source)


@router.patch("/sources/{source_id}", response_model=DataSourceResponse)
async def edit_source(
    source_id: UUID,
    payload: DataSourceUpdateRequest,
    request: Request,
    session: DBSession,
    auth: CSRFProtectedAuth,
) -> DataSourceResponse:
    source = await _source_or_404(session, auth, source_id, "integration.edit")
    await update_data_source(
        session,
        source=source,
        auth=auth,
        payload=payload,
        correlation_id=_correlation_id(request),
    )
    return await source_response(session, source)


@router.post("/sources/{source_id}/test", response_model=ConnectionTestResponse)
async def test_source(
    source_id: UUID, session: DBSession, auth: CSRFProtectedAuth
) -> ConnectionTestResponse:
    source = await _source_or_404(session, auth, source_id, "integration.test")
    require_scope_access(
        auth, "integration.test", company_id=source.company_id, branch_id=source.branch_id
    )
    result = await test_data_source_connection(session, source)
    return ConnectionTestResponse(
        healthy=result.healthy,
        latency_ms=result.latency_ms,
        message=result.message,
        checked_at=result.checked_at,
    )


@router.post("/mappings/validate", response_model=MessageResponse)
async def validate_mapping(
    payload: MappingCreateRequest, session: DBSession, auth: CSRFProtectedAuth
) -> MessageResponse:
    source = await _source_or_404(session, auth, payload.data_source_id, "integration.mapping")
    require_scope_access(
        auth, "integration.mapping", company_id=source.company_id, branch_id=source.branch_id
    )
    validate_mapping_fields(payload.fields, payload.dataset_type)
    return MessageResponse(message="Mapping is valid")


@router.post("/mappings", response_model=MappingResponse, status_code=status.HTTP_201_CREATED)
async def add_mapping(
    payload: MappingCreateRequest, session: DBSession, auth: CSRFProtectedAuth
) -> MappingResponse:
    return await create_mapping(session, auth=auth, payload=payload)


@router.get("/mappings", response_model=list[MappingResponse])
async def list_mappings(session: DBSession, auth: Reader) -> list[MappingResponse]:
    sources = select(DataSource.id).where(
        integration_source_visibility_filter(auth, "integration.view")
    )
    rows = (
        await session.execute(
            select(MappingProfile, MappingVersion)
            .join(MappingVersion, MappingVersion.mapping_profile_id == MappingProfile.id)
            .where(MappingProfile.data_source_id.in_(sources))
            .order_by(MappingProfile.name, MappingVersion.version_number.desc())
        )
    ).all()
    responses: list[MappingResponse] = []
    for profile, version in rows:
        fields = list(
            (
                await session.scalars(
                    select(FieldMapping)
                    .where(FieldMapping.mapping_version_id == version.id)
                    .order_by(FieldMapping.source_field)
                )
            ).all()
        )
        responses.append(
            MappingResponse(
                id=profile.id,
                version_id=version.id,
                data_source_id=profile.data_source_id,
                name=profile.name,
                dataset_type=profile.dataset_type,
                version_number=version.version_number,
                status=version.status,
                fields=[
                    {
                        "source_field": field.source_field,
                        "target_entity": field.target_entity,
                        "target_field": field.target_field,
                        "transform_type": field.transform_type,
                        "transform_config": field.transform_config,
                        "required": field.required,
                        "default_value": field.default_value,
                    }
                    for field in fields
                ],
            )
        )
    return responses


@router.post("/sources/{source_id}/sync", response_model=ImportBatchResponse)
async def sync_source(
    source_id: UUID,
    payload: SyncStartRequest,
    request: Request,
    session: DBSession,
    auth: CSRFProtectedAuth,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=180)],
) -> ImportBatchResponse:
    source = await _source_or_404(session, auth, source_id, "integration.sync")
    batch, _ = await start_sync(
        session,
        auth=auth,
        source=source,
        request=payload,
        idempotency_key=idempotency_key,
        correlation_id=_correlation_id(request),
    )
    return ImportBatchResponse.model_validate(batch)


async def _stream_upload(upload: UploadFile, path: Path, maximum_size: int) -> tuple[int, str]:
    size = 0
    digest = sha256()
    with path.open("wb") as output:
        while chunk := await upload.read(1_048_576):
            size += len(chunk)
            if size > maximum_size:
                raise AppError(
                    code="upload_too_large",
                    message="Upload exceeds the configured limit",
                    status_code=413,
                )
            digest.update(chunk)
            output.write(chunk)
    if size == 0:
        raise AppError(code="empty_upload", message="Upload is empty", status_code=422)
    return size, digest.hexdigest()


@router.post("/sources/{source_id}/upload", response_model=ImportBatchResponse)
async def upload_source_file(
    source_id: UUID,
    request: Request,
    session: DBSession,
    auth: CSRFProtectedAuth,
    file: Annotated[UploadFile, File()],
    dataset_type: Annotated[
        str, Form(pattern="^(product|supplier|sale|purchase|stock|price|all)$")
    ],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=180)],
) -> ImportBatchResponse:
    source = await _source_or_404(session, auth, source_id, "integration.sync")
    require_scope_access(
        auth, "integration.sync", company_id=source.company_id, branch_id=source.branch_id
    )
    instance = await session.get(ConnectorInstance, source.connector_instance_id)
    definition = (
        await session.get(ConnectorDefinition, instance.connector_definition_id)
        if instance
        else None
    )
    if definition is None or definition.connector_key != "file-upload":
        raise AppError(
            code="not_upload_source", message="Data source does not accept files", status_code=409
        )
    content_type = (file.content_type or "application/octet-stream").split(";", 1)[0]
    original_name = Path(file.filename or "upload").name
    extension = Path(original_name).suffix.casefold()
    if extension not in _ALLOWED_EXTENSIONS:
        raise AppError(
            code="unsupported_file",
            message="Only CSV, JSON and NDJSON are accepted",
            status_code=415,
        )
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise AppError(
            code="unsupported_content_type",
            message="Uploaded content type is not allowed",
            status_code=415,
        )
    existing_by_key = await session.scalar(
        select(ImportBatch).where(
            ImportBatch.tenant_id == source.tenant_id,
            ImportBatch.data_source_id == source.id,
            ImportBatch.idempotency_key == idempotency_key,
        )
    )
    if existing_by_key is not None:
        return ImportBatchResponse.model_validate(existing_by_key)
    settings = get_settings()
    temporary_path: Path | None = None
    stored_key: str | None = None
    stored_new = False
    try:
        with tempfile.NamedTemporaryFile(
            prefix="pharma-upload-", suffix=extension, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        size, digest = await _stream_upload(
            file, temporary_path, settings.integration_upload_max_bytes
        )
        duplicate = await session.scalar(
            select(ImportedFile).where(
                ImportedFile.tenant_id == source.tenant_id,
                ImportedFile.data_source_id == source.id,
                ImportedFile.content_sha256 == digest,
            )
        )
        if duplicate is not None:
            existing_batch = await session.get(ImportBatch, duplicate.batch_id)
            if existing_batch is None:
                raise RuntimeError("Imported file invariant violated")
            return ImportBatchResponse.model_validate(existing_batch)
        safe_name = _SAFE_NAME.sub("-", original_name).strip(".-")[:120] or f"upload{extension}"
        stored_key = (
            f"landing/{source.tenant_id}/{source.id}/{date.today():%Y/%m/%d}/{digest}/{safe_name}"
        )
        storage = get_object_storage()
        stored = storage.put_file(
            temporary_path,
            key=stored_key,
            content_type=content_type,
            metadata={
                "sha256": digest,
                "tenant-id": str(source.tenant_id),
                "data-source-id": str(source.id),
            },
        )
        stored_new = True
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
            content_hash=digest,
            dataset_type=dataset_type,
            state=ProcessingState.CREATED.value,
            correlation_id=_correlation_id(request),
        )
        session.add(batch)
        await session.flush()
        imported_file = ImportedFile(
            tenant_id=source.tenant_id,
            batch_id=batch.id,
            data_source_id=source.id,
            original_filename=safe_name,
            object_bucket=stored.bucket,
            object_key=stored.key,
            content_type=content_type,
            size_bytes=size,
            content_sha256=digest,
            immutable=True,
            retention_until=date.today() + timedelta(days=settings.integration_retention_days),
        )
        session.add(imported_file)
        await session.flush()
        session.add(
            LandingManifest(
                tenant_id=source.tenant_id,
                batch_id=batch.id,
                imported_file_id=imported_file.id,
                record_count=0,
                payload_sha256=digest,
                connector_version=definition.version,
                source_schema_version=definition.schema_version,
                metadata_json={"upload": True, "filename": safe_name, "size_bytes": size},
            )
        )
        await transition_batch(
            session,
            batch,
            ProcessingState.QUEUED,
            actor_type="user",
            actor_id=str(auth.user.id),
        )
        await transition_batch(
            session,
            batch,
            ProcessingState.RECEIVED,
            actor_type="api",
            actor_id="upload",
        )
        await session.flush()
        await session.refresh(batch)
        await session.commit()
        from pharma_api.infrastructure.integrations.tasks import parse_batch

        parse_batch.send(str(batch.id), str(batch.tenant_id), _correlation_id(request) or "")
        return ImportBatchResponse.model_validate(batch)
    except Exception:
        await session.rollback()
        if stored_new and stored_key is not None:
            get_object_storage().delete_object(stored_key)
        raise
    finally:
        await file.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


@router.get("/batches", response_model=Page[ImportBatchResponse])
async def list_batches(
    session: DBSession,
    auth: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    state_filter: Annotated[str | None, Query(alias="state")] = None,
) -> Page[ImportBatchResponse]:
    filters = [integration_batch_visibility_filter(auth, "integration.view")]
    if state_filter:
        filters.append(ImportBatch.state == state_filter)
    total = int(
        await session.scalar(select(func.count()).select_from(ImportBatch).where(*filters)) or 0
    )
    batches = list(
        (
            await session.scalars(
                select(ImportBatch)
                .where(*filters)
                .order_by(ImportBatch.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    return Page(
        items=[ImportBatchResponse.model_validate(batch) for batch in batches],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/batches/{batch_id}", response_model=ImportBatchResponse)
async def get_batch(batch_id: UUID, session: DBSession, auth: Reader) -> ImportBatchResponse:
    return ImportBatchResponse.model_validate(await _batch_or_404(session, auth, batch_id))


@router.post("/batches/{batch_id}/cancel", response_model=ImportBatchResponse)
async def cancel_import_batch(
    batch_id: UUID,
    request: Request,
    session: DBSession,
    auth: CSRFProtectedAuth,
) -> ImportBatchResponse:
    batch = await _batch_or_404(session, auth, batch_id, "integration.cancel")
    await cancel_batch(session, auth=auth, batch=batch, correlation_id=_correlation_id(request))
    return ImportBatchResponse.model_validate(batch)


@router.post("/batches/{batch_id}/reprocess", response_model=ImportBatchResponse)
async def replay_import_batch(
    batch_id: UUID,
    request: Request,
    session: DBSession,
    auth: CSRFProtectedAuth,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=180)],
) -> ImportBatchResponse:
    parent = await _batch_or_404(session, auth, batch_id, "integration.reprocess")
    batch, _ = await reprocess_batch(
        session,
        auth=auth,
        parent=parent,
        idempotency_key=idempotency_key,
        correlation_id=_correlation_id(request),
    )
    return ImportBatchResponse.model_validate(batch)


@router.get("/batches/{batch_id}/errors", response_model=list[ProcessingErrorResponse])
async def list_batch_errors(
    batch_id: UUID, session: DBSession, auth: ErrorReader
) -> list[ProcessingErrorResponse]:
    await _batch_or_404(session, auth, batch_id, "integration.errors")
    errors = list(
        (
            await session.scalars(
                select(ProcessingError)
                .where(ProcessingError.batch_id == batch_id)
                .order_by(ProcessingError.created_at.desc())
                .limit(500)
            )
        ).all()
    )
    return [ProcessingErrorResponse.model_validate(item) for item in errors]


@router.get("/batches/{batch_id}/rejections", response_model=list[RejectedRecordResponse])
async def list_batch_rejections(
    batch_id: UUID, session: DBSession, auth: ErrorReader
) -> list[RejectedRecordResponse]:
    await _batch_or_404(session, auth, batch_id, "integration.errors")
    rejected = list(
        (
            await session.scalars(
                select(RejectedRecord)
                .where(RejectedRecord.batch_id == batch_id)
                .order_by(RejectedRecord.created_at.desc())
                .limit(500)
            )
        ).all()
    )
    return [RejectedRecordResponse.model_validate(item) for item in rejected]


@router.patch("/rejections/{rejection_id}", response_model=RejectedRecordResponse)
async def correct_rejection(
    rejection_id: UUID,
    payload: RejectedCorrectionRequest,
    session: DBSession,
    auth: CSRFProtectedAuth,
) -> RejectedRecordResponse:
    rejected = await session.get(RejectedRecord, rejection_id)
    if rejected is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    await correct_rejected_record(
        session,
        auth=auth,
        rejected=rejected,
        correction=payload.correction_payload,
        expected_version=payload.expected_version,
    )
    return RejectedRecordResponse.model_validate(rejected)


@router.get("/batches/{batch_id}/quality", response_model=list[QualityResultResponse])
async def list_batch_quality(
    batch_id: UUID, session: DBSession, auth: QualityReader
) -> list[QualityResultResponse]:
    await _batch_or_404(session, auth, batch_id, "integration.quality")
    results = list(
        (
            await session.scalars(
                select(QualityResult)
                .where(QualityResult.batch_id == batch_id)
                .order_by(QualityResult.entity_type, QualityResult.rule_key)
            )
        ).all()
    )
    return [QualityResultResponse.model_validate(item) for item in results]


@router.get("/batches/{batch_id}/lineage", response_model=list[LineageResponse])
async def list_batch_lineage(
    batch_id: UUID, session: DBSession, auth: Reader
) -> list[LineageResponse]:
    await _batch_or_404(session, auth, batch_id)
    lineage = list(
        (
            await session.scalars(
                select(LineageEvent)
                .where(LineageEvent.batch_id == batch_id)
                .order_by(LineageEvent.created_at)
                .limit(1_000)
            )
        ).all()
    )
    return [LineageResponse.model_validate(item) for item in lineage]


async def _raw_file(session: DBSession, auth: AuthContext, batch_id: UUID) -> ImportedFile:
    await _batch_or_404(session, auth, batch_id, "integration.raw")
    imported_file = await session.scalar(
        select(ImportedFile)
        .join(LandingManifest, LandingManifest.imported_file_id == ImportedFile.id)
        .where(LandingManifest.batch_id == batch_id)
    )
    if imported_file is None:
        raise AppError(code="not_found", message="Landing file not found", status_code=404)
    return imported_file


async def _audit_raw_access(
    session: DBSession, auth: AuthContext, request: Request, batch_id: UUID
) -> None:
    await append_audit_event(
        session,
        AuditRecord(
            action="integration.raw.accessed",
            category="integration_security",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=auth.tenant_id,
            company_id=auth.company_id,
            branch_id=auth.branch_id,
            resource_type="import_batch",
            resource_id=str(batch_id),
            correlation_id=_correlation_id(request),
        ),
    )


@router.get("/batches/{batch_id}/raw", response_model=RawPayloadResponse)
async def raw_payload_metadata(
    batch_id: UUID, request: Request, session: DBSession, auth: RawReader
) -> RawPayloadResponse:
    imported_file = await _raw_file(session, auth, batch_id)
    await _audit_raw_access(session, auth, request, batch_id)
    url = get_object_storage().presigned_download(imported_file.object_key, expires_seconds=60)
    if url is None:
        url = f"/api/v1/integrations/batches/{batch_id}/raw/download"
    return RawPayloadResponse(
        file_id=imported_file.id,
        filename=imported_file.original_filename,
        content_type=imported_file.content_type,
        size_bytes=imported_file.size_bytes,
        content_sha256=imported_file.content_sha256,
        retention_until=imported_file.retention_until,
        download_url=url,
    )


@router.get("/batches/{batch_id}/raw/download")
async def download_raw_payload(
    batch_id: UUID, request: Request, session: DBSession, auth: RawReader
) -> StreamingResponse:
    imported_file = await _raw_file(session, auth, batch_id)
    await _audit_raw_access(session, auth, request, batch_id)
    iterator = get_object_storage().iter_object(imported_file.object_key)
    return StreamingResponse(
        iterator,
        media_type=imported_file.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{imported_file.original_filename}"',
            "X-Content-SHA256": imported_file.content_sha256,
        },
    )


def _safe_csv(value: Any) -> str:
    rendered = "" if value is None else str(value)
    if rendered.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{rendered}"
    return rendered


@router.get("/batches/{batch_id}/report.csv")
async def export_batch_report(
    batch_id: UUID, session: DBSession, auth: Exporter
) -> StreamingResponse:
    batch = await _batch_or_404(session, auth, batch_id, "integration.export")
    errors = list(
        (
            await session.scalars(
                select(ProcessingError)
                .where(ProcessingError.batch_id == batch.id)
                .order_by(ProcessingError.created_at)
                .limit(10_000)
            )
        ).all()
    )
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["batch_id", "state", "step", "entity", "field", "code", "severity", "message"])
    if not errors:
        writer.writerow([str(batch.id), batch.state, "", "", "", "", "", ""])
    for error in errors:
        writer.writerow(
            [
                _safe_csv(batch.id),
                _safe_csv(batch.state),
                _safe_csv(error.step_name),
                _safe_csv(error.entity_type),
                _safe_csv(error.field_name),
                _safe_csv(error.error_code),
                _safe_csv(error.severity),
                _safe_csv(error.message),
            ]
        )
    payload = output.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        iter((payload,)),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="batch-{batch.id}.csv"'},
    )


def _model_dict(model: Any, columns: tuple[str, ...]) -> dict[str, Any]:
    return {column: getattr(model, column) for column in columns}


def _encode_cursor(sort_at: datetime, record_id: UUID) -> str:
    payload = json.dumps(
        {"at": sort_at.isoformat(), "id": str(record_id)}, separators=(",", ":")
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str | None) -> tuple[datetime, UUID] | None:
    if value is None:
        return None
    try:
        padding = "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(value + padding))
        parsed = datetime.fromisoformat(str(payload["at"]).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or UTC), UUID(str(payload["id"]))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise AppError(code="invalid_cursor", message="Cursor is invalid", status_code=422) from exc


def _next_cursor(rows: list[Any], sort_field: str, limit: int) -> str | None:
    if len(rows) <= limit:
        return None
    last = rows[limit - 1]
    return _encode_cursor(getattr(last, sort_field), last.id)


@router.get("/canonical/products", response_model=CursorPage[dict[str, Any]])
async def list_canonical_products(
    session: DBSession,
    auth: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> CursorPage[dict[str, Any]]:
    visible_sources = select(DataSource.id).where(
        integration_source_visibility_filter(auth, "integration.view")
    )
    filters: list[ColumnElement[bool]] = [Product.data_source_id.in_(visible_sources)]
    decoded = _decode_cursor(cursor)
    if decoded:
        filters.append(
            or_(
                Product.created_at < decoded[0],
                and_(Product.created_at == decoded[0], Product.id < decoded[1]),
            )
        )
    products = list(
        (
            await session.scalars(
                select(Product)
                .where(*filters)
                .order_by(Product.created_at.desc(), Product.id.desc())
                .limit(limit + 1)
            )
        ).all()
    )
    columns = ("id", "company_id", "branch_id", "sku", "name", "base_unit", "commercial_status")
    return CursorPage(
        items=[_model_dict(item, columns) for item in products[:limit]],
        next_cursor=_next_cursor(products, "created_at", limit),
        limit=limit,
    )


@router.get("/canonical/suppliers", response_model=CursorPage[dict[str, Any]])
async def list_canonical_suppliers(
    session: DBSession,
    auth: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> CursorPage[dict[str, Any]]:
    visible_sources = select(DataSource.id).where(
        integration_source_visibility_filter(auth, "integration.view")
    )
    filters: list[ColumnElement[bool]] = [Supplier.data_source_id.in_(visible_sources)]
    decoded = _decode_cursor(cursor)
    if decoded:
        filters.append(
            or_(
                Supplier.created_at < decoded[0],
                and_(Supplier.created_at == decoded[0], Supplier.id < decoded[1]),
            )
        )
    rows = list(
        (
            await session.scalars(
                select(Supplier)
                .where(*filters)
                .order_by(Supplier.created_at.desc(), Supplier.id.desc())
                .limit(limit + 1)
            )
        ).all()
    )
    columns = ("id", "company_id", "external_id", "name", "status", "commercial_terms")
    return CursorPage(
        items=[_model_dict(item, columns) for item in rows[:limit]],
        next_cursor=_next_cursor(rows, "created_at", limit),
        limit=limit,
    )


@router.get("/canonical/sales", response_model=CursorPage[dict[str, Any]])
async def list_canonical_sales(
    session: DBSession,
    auth: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> CursorPage[dict[str, Any]]:
    visible_sources = select(DataSource.id).where(
        integration_source_visibility_filter(auth, "integration.view")
    )
    filters: list[ColumnElement[bool]] = [Sale.data_source_id.in_(visible_sources)]
    decoded = _decode_cursor(cursor)
    if decoded:
        filters.append(
            or_(
                Sale.occurred_at < decoded[0],
                and_(Sale.occurred_at == decoded[0], Sale.id < decoded[1]),
            )
        )
    sales = list(
        (
            await session.scalars(
                select(Sale)
                .where(*filters)
                .order_by(Sale.occurred_at.desc(), Sale.id.desc())
                .limit(limit + 1)
            )
        ).all()
    )
    columns = (
        "id",
        "company_id",
        "branch_id",
        "external_id",
        "occurred_at",
        "channel",
        "status",
        "gross_total",
        "net_total",
    )
    return CursorPage(
        items=[_model_dict(item, columns) for item in sales[:limit]],
        next_cursor=_next_cursor(sales, "occurred_at", limit),
        limit=limit,
    )


@router.get("/canonical/purchases", response_model=CursorPage[dict[str, Any]])
async def list_canonical_purchases(
    session: DBSession,
    auth: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> CursorPage[dict[str, Any]]:
    visible_sources = select(DataSource.id).where(
        integration_source_visibility_filter(auth, "integration.view")
    )
    filters: list[ColumnElement[bool]] = [PurchaseOrder.data_source_id.in_(visible_sources)]
    decoded = _decode_cursor(cursor)
    if decoded:
        filters.append(
            or_(
                PurchaseOrder.ordered_at < decoded[0],
                and_(PurchaseOrder.ordered_at == decoded[0], PurchaseOrder.id < decoded[1]),
            )
        )
    rows = list(
        (
            await session.scalars(
                select(PurchaseOrder)
                .where(*filters)
                .order_by(PurchaseOrder.ordered_at.desc(), PurchaseOrder.id.desc())
                .limit(limit + 1)
            )
        ).all()
    )
    columns = (
        "id",
        "company_id",
        "branch_id",
        "supplier_id",
        "external_id",
        "status",
        "ordered_at",
        "net_total",
    )
    return CursorPage(
        items=[_model_dict(item, columns) for item in rows[:limit]],
        next_cursor=_next_cursor(rows, "ordered_at", limit),
        limit=limit,
    )


@router.get("/canonical/inventory", response_model=CursorPage[dict[str, Any]])
async def list_canonical_inventory(
    session: DBSession,
    auth: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> CursorPage[dict[str, Any]]:
    visible_sources = select(DataSource.id).where(
        integration_source_visibility_filter(auth, "integration.view")
    )
    filters: list[ColumnElement[bool]] = [StockBalance.data_source_id.in_(visible_sources)]
    decoded = _decode_cursor(cursor)
    if decoded:
        filters.append(
            or_(
                StockBalance.updated_at < decoded[0],
                and_(StockBalance.updated_at == decoded[0], StockBalance.id < decoded[1]),
            )
        )
    balances = list(
        (
            await session.scalars(
                select(StockBalance)
                .where(*filters)
                .order_by(StockBalance.updated_at.desc(), StockBalance.id.desc())
                .limit(limit + 1)
            )
        ).all()
    )
    columns = (
        "id",
        "company_id",
        "branch_id",
        "product_id",
        "on_hand",
        "reserved",
        "in_transit",
        "updated_from_source_at",
    )
    return CursorPage(
        items=[_model_dict(item, columns) for item in balances[:limit]],
        next_cursor=_next_cursor(balances, "updated_at", limit),
        limit=limit,
    )


@router.get("/canonical/prices", response_model=CursorPage[dict[str, Any]])
async def list_canonical_prices(
    session: DBSession,
    auth: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> CursorPage[dict[str, Any]]:
    visible_sources = select(DataSource.id).where(
        integration_source_visibility_filter(auth, "integration.view")
    )
    filters: list[ColumnElement[bool]] = [ProductPrice.data_source_id.in_(visible_sources)]
    decoded = _decode_cursor(cursor)
    if decoded:
        filters.append(
            or_(
                ProductPrice.valid_from < decoded[0],
                and_(ProductPrice.valid_from == decoded[0], ProductPrice.id < decoded[1]),
            )
        )
    rows = list(
        (
            await session.scalars(
                select(ProductPrice)
                .where(*filters)
                .order_by(ProductPrice.valid_from.desc(), ProductPrice.id.desc())
                .limit(limit + 1)
            )
        ).all()
    )
    columns = (
        "id",
        "company_id",
        "branch_id",
        "product_id",
        "price",
        "reference_price",
        "reference_cost",
        "valid_from",
        "valid_to",
        "current",
    )
    return CursorPage(
        items=[_model_dict(item, columns) for item in rows[:limit]],
        next_cursor=_next_cursor(rows, "valid_from", limit),
        limit=limit,
    )
