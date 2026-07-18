from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import tempfile
from collections import Counter
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4, uuid5

import dramatiq
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.integrations.connectors import (
    ConnectorEnvelope,
    ExtractionRequest,
    connector_registry,
)
from pharma_api.application.integrations.quality import QualityContext, QualityEngine
from pharma_api.application.integrations.service import transition_batch
from pharma_api.core.config import get_settings
from pharma_api.core.logging import configure_logging, get_logger
from pharma_api.domain.integrations.state_machine import ProcessingState, is_terminal_state
from pharma_api.infrastructure.db.context import RLSContext, apply_rls_context
from pharma_api.infrastructure.db.models.canonical import (
    Brand,
    Category,
    InventoryLot,
    InventoryMovement,
    Manufacturer,
    Product,
    ProductIdentifier,
    ProductPresentation,
    ProductPrice,
    Promotion,
    PromotionProduct,
    PurchaseItem,
    PurchaseOrder,
    PurchaseReceipt,
    Sale,
    SaleAdjustment,
    SaleItem,
    SalePayment,
    StockBalance,
    StockSnapshot,
    Supplier,
    SupplierCost,
    SupplierIdentifier,
    SupplierProduct,
)
from pharma_api.infrastructure.db.models.integration import (
    ConnectorDefinition,
    ConnectorInstance,
    DataSource,
    DeadLetter,
    FieldMapping,
    ImportBatch,
    ImportedFile,
    LandingManifest,
    LineageEvent,
    OutboxEvent,
    ProcessingError,
    ProcessingStatistic,
    ProcessingStep,
    QualityResult,
    RejectedRecord,
    StagingRecord,
    SyncCheckpoint,
    SyncCursor,
    SyncExecution,
)
from pharma_api.infrastructure.db.session import get_session_factory
from pharma_api.infrastructure.messaging.broker import configure_broker
from pharma_api.infrastructure.object_storage import (
    ObjectAlreadyExistsError,
    StoredObject,
    get_object_storage,
)

configure_broker()
configure_logging(get_settings().app_log_level)
logger = get_logger(__name__)
quality_engine = QualityEngine()

_ENTITY_ORDER = {"product": 0, "supplier": 1, "sale": 2, "purchase": 3, "stock": 4, "price": 5}
_ALLOWED_UPLOAD_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/json",
    "application/x-ndjson",
    "text/plain",
}


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _tenant_session(tenant_id: UUID) -> AsyncSession:
    session = get_session_factory()()
    await apply_rls_context(session, RLSContext(tenant_id=tenant_id))
    return session


async def _start_step(
    session: AsyncSession, batch: ImportBatch, step_name: str, state: ProcessingState
) -> ProcessingStep:
    attempt = (
        int(
            await session.scalar(
                select(func.count(ProcessingStep.id)).where(
                    ProcessingStep.batch_id == batch.id,
                    ProcessingStep.step_name == step_name,
                )
            )
            or 0
        )
        + 1
    )
    step = ProcessingStep(
        tenant_id=batch.tenant_id,
        batch_id=batch.id,
        step_name=step_name,
        sequence_number=_ENTITY_ORDER.get(step_name, 0),
        attempt_number=attempt,
        state=state.value,
        started_at=datetime.now(UTC),
    )
    session.add(step)
    return step


def _finish_step(step: ProcessingStep, state: ProcessingState) -> None:
    step.state = state.value
    step.completed_at = datetime.now(UTC)


async def _record_failure(
    batch_id: UUID,
    tenant_id: UUID,
    step_name: str,
    exc: Exception,
    *,
    final_attempt: int = 5,
) -> None:
    session = await _tenant_session(tenant_id)
    try:
        batch = await session.scalar(
            select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update()
        )
        if batch is None or is_terminal_state(batch.state):
            return
        failures = (
            int(
                await session.scalar(
                    select(func.count(ProcessingError.id)).where(
                        ProcessingError.batch_id == batch_id,
                        ProcessingError.step_name == step_name,
                        ProcessingError.error_class == "worker_failure",
                    )
                )
                or 0
            )
            + 1
        )
        session.add(
            ProcessingError(
                tenant_id=tenant_id,
                batch_id=batch_id,
                step_name=step_name,
                error_class="worker_failure",
                error_code=type(exc).__name__[:100],
                severity="error" if failures < final_attempt else "blocking",
                message=str(exc)[:800] or type(exc).__name__,
                retryable=failures < final_attempt,
            )
        )
        target = ProcessingState.RETRY_SCHEDULED
        if failures >= final_attempt:
            target = ProcessingState.FAILED
            session.add(
                DeadLetter(
                    tenant_id=tenant_id,
                    batch_id=batch_id,
                    step_name=step_name,
                    error_class=type(exc).__name__,
                    reason=str(exc)[:800] or type(exc).__name__,
                    payload_reference=f"import-batch:{batch_id}",
                    retry_count=failures,
                    status="open",
                )
            )
        await transition_batch(
            session,
            batch,
            target,
            actor_type="worker",
            actor_id=os.getenv("HOSTNAME", "local-worker"),
            reason=f"{step_name}:{type(exc).__name__}",
        )
        await session.commit()
    finally:
        await session.close()


def _actor_failure(batch_id: str, tenant_id: str, step_name: str, exc: Exception) -> None:
    logger.error(
        "integration_step_failed",
        tenant_id=tenant_id,
        batch_id=batch_id,
        step=step_name,
        error_class=type(exc).__name__,
    )
    _run(_record_failure(UUID(batch_id), UUID(tenant_id), step_name, exc))


def _serialize_envelope(envelope: ConnectorEnvelope) -> bytes:
    document = {
        "entity_type": envelope.entity_type,
        "external_id": envelope.external_id,
        "source_version": envelope.source_version,
        "occurred_at": envelope.occurred_at.isoformat(),
        "payload": dict(envelope.payload),
        "page": envelope.page,
        "sequence": envelope.sequence,
        "content_hash": envelope.content_hash,
    }
    return (json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


async def _acquire_batch(batch_id: UUID, tenant_id: UUID, correlation_id: str) -> None:
    session = await _tenant_session(tenant_id)
    try:
        batch = await session.scalar(
            select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update()
        )
        if batch is None or is_terminal_state(batch.state):
            return
        if batch.cancel_requested:
            await transition_batch(
                session,
                batch,
                ProcessingState.CANCELLED,
                actor_type="worker",
                actor_id="acquire",
            )
            await session.commit()
            return
        if batch.state in {
            ProcessingState.RETRY_SCHEDULED.value,
            ProcessingState.QUEUED.value,
        }:
            await transition_batch(
                session,
                batch,
                ProcessingState.CONNECTING,
                actor_type="worker",
                actor_id="acquire",
            )
        else:
            return
        step = await _start_step(session, batch, "acquire", ProcessingState.CONNECTING)
        await transition_batch(
            session,
            batch,
            ProcessingState.EXTRACTING,
            actor_type="worker",
            actor_id="acquire",
        )
        source = await session.get(DataSource, batch.data_source_id)
        if source is None:
            raise RuntimeError("Data source not found")
        instance = await session.get(ConnectorInstance, source.connector_instance_id)
        if instance is None:
            raise RuntimeError("Connector instance not found")
        definition = await session.get(ConnectorDefinition, instance.connector_definition_id)
        execution = await session.scalar(
            select(SyncExecution).where(SyncExecution.batch_id == batch.id)
        )
        if definition is None or execution is None:
            raise RuntimeError("Execution connector invariant violated")
        connector_key = definition.connector_key
        connector_version = definition.version
        schema_version = definition.schema_version
        execution_id = execution.id
        request_options = execution.request_options
        configuration = dict(instance.configuration)
        data_source_id = source.id
        source_scope = (source.company_id, source.branch_id, source.dataset_type)
        _finish_step(step, ProcessingState.EXTRACTING)
        await session.commit()
    finally:
        await session.close()

    entities = tuple(request_options.get("entities") or ())
    if not entities:
        entities = (
            (source_scope[2],)
            if source_scope[2] != "all"
            else ("product", "supplier", "sale", "purchase", "stock", "price")
        )
    connector = connector_registry.get(connector_key)
    request = ExtractionRequest(
        tenant_id=str(tenant_id),
        company_id=str(source_scope[0]),
        branch_id=str(source_scope[1]) if source_scope[1] else None,
        entities=entities,
        mode=execution.mode,
        start_at=execution.range_start,
        end_at=execution.range_end,
        page_size=get_settings().integration_chunk_records,
        timeout_seconds=get_settings().connector_timeout_seconds,
        configuration=configuration,
    )
    digest = sha256()
    record_count = 0
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="pharma-landing-", suffix=".ndjson", delete=False
        ) as output:
            temp_path = Path(output.name)
            for envelope in connector.extract(request):
                line = _serialize_envelope(envelope)
                digest.update(line)
                output.write(line)
                record_count += 1
        content_hash = digest.hexdigest()
        object_key = f"{tenant_id}/{data_source_id}/sha256/{content_hash}.ndjson"
        lookup_session = await _tenant_session(tenant_id)
        try:
            landing_exists = (
                await lookup_session.scalar(
                    select(ImportedFile.id).where(
                        ImportedFile.data_source_id == data_source_id,
                        ImportedFile.content_sha256 == content_hash,
                    )
                )
                is not None
            )
        finally:
            await lookup_session.close()
        storage = get_object_storage()
        stored: StoredObject | None = None
        if not landing_exists:
            try:
                stored = storage.put_file(
                    temp_path,
                    key=object_key,
                    content_type="application/x-ndjson",
                    metadata={
                        "tenant_id": str(tenant_id),
                        "batch_id": str(batch_id),
                        "correlation_id": correlation_id,
                    },
                )
            except ObjectAlreadyExistsError:
                stored = StoredObject(
                    bucket=storage.bucket,
                    key=object_key,
                    size_bytes=temp_path.stat().st_size,
                    content_type="application/x-ndjson",
                )

        session = await _tenant_session(tenant_id)
        try:
            batch = await session.scalar(
                select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update()
            )
            if batch is None:
                return
            source = await session.get(DataSource, batch.data_source_id)
            existing_file = await session.scalar(
                select(ImportedFile).where(
                    ImportedFile.data_source_id == batch.data_source_id,
                    ImportedFile.content_sha256 == content_hash,
                )
            )
            imported_file = existing_file
            if imported_file is None:
                if stored is None:
                    raise RuntimeError("Landing object metadata is missing")
                imported_file = ImportedFile(
                    tenant_id=tenant_id,
                    batch_id=batch.id,
                    data_source_id=batch.data_source_id,
                    original_filename=f"{connector_key}-{batch.id}.ndjson",
                    object_bucket=stored.bucket,
                    object_key=stored.key,
                    content_type=stored.content_type,
                    size_bytes=stored.size_bytes,
                    content_sha256=content_hash,
                    immutable=True,
                    retention_until=date.today()
                    + timedelta(days=get_settings().integration_retention_days),
                )
                session.add(imported_file)
                await session.flush()
            session.add(
                LandingManifest(
                    tenant_id=tenant_id,
                    batch_id=batch.id,
                    imported_file_id=imported_file.id,
                    record_count=record_count,
                    payload_sha256=content_hash,
                    connector_version=connector_version,
                    source_schema_version=schema_version,
                    metadata_json={"connector": connector_key, "entities": list(entities)},
                )
            )
            batch.content_hash = content_hash
            batch.received_records = record_count
            batch.progress_percent = 15
            extract_checkpoint = insert(SyncCheckpoint).values(
                id=uuid5(execution_id, "checkpoint:extract"),
                tenant_id=tenant_id,
                execution_id=execution_id,
                step_name="extract",
                cursor_value=str(record_count),
                page_number=max(1, (record_count - 1) // request.page_size + 1),
                records_committed=record_count,
                source_version=schema_version,
            )
            await session.execute(
                extract_checkpoint.on_conflict_do_update(
                    index_elements=["tenant_id", "execution_id", "step_name"],
                    set_={
                        "cursor_value": extract_checkpoint.excluded.cursor_value,
                        "page_number": extract_checkpoint.excluded.page_number,
                        "records_committed": record_count,
                        "source_version": schema_version,
                        "updated_at": func.now(),
                    },
                )
            )
            source_cursor = insert(SyncCursor).values(
                id=uuid5(batch.data_source_id, "cursor:default"),
                tenant_id=tenant_id,
                data_source_id=batch.data_source_id,
                cursor_key="default",
                cursor_value=str(record_count),
                source_version=schema_version,
                page_number=max(1, (record_count - 1) // request.page_size + 1),
            )
            await session.execute(
                source_cursor.on_conflict_do_update(
                    index_elements=["tenant_id", "data_source_id", "cursor_key"],
                    set_={
                        "cursor_value": source_cursor.excluded.cursor_value,
                        "source_version": schema_version,
                        "page_number": source_cursor.excluded.page_number,
                        "updated_at": func.now(),
                    },
                )
            )
            await transition_batch(
                session,
                batch,
                ProcessingState.RECEIVED,
                actor_type="worker",
                actor_id="acquire",
            )
            if source is not None:
                source.last_sync_at = datetime.now(UTC)
            await session.commit()
        finally:
            await session.close()
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    parse_batch.send(str(batch_id), str(tenant_id), correlation_id)


@dramatiq.actor(
    queue_name="integration-acquire",
    max_retries=5,
    min_backoff=2_000,
    max_backoff=120_000,
    time_limit=900_000,
)
def acquire_batch(batch_id: str, tenant_id: str, correlation_id: str = "") -> None:
    try:
        _run(_acquire_batch(UUID(batch_id), UUID(tenant_id), correlation_id))
    except Exception as exc:
        _actor_failure(batch_id, tenant_id, "acquire", exc)
        raise


def _materialize_object(imported_file: ImportedFile) -> Path:
    suffix = Path(imported_file.original_filename).suffix.casefold() or ".data"
    with tempfile.NamedTemporaryFile(prefix="pharma-parse-", suffix=suffix, delete=False) as output:
        path = Path(output.name)
        for chunk in get_object_storage().iter_object(imported_file.object_key):
            output.write(chunk)
    return path


def _stream_json_array(source: io.TextIOBase) -> Iterator[dict[str, Any]]:
    decoder = json.JSONDecoder()
    buffer = ""
    started = False
    finished = False
    while not finished:
        chunk = source.read(65_536)
        if not chunk and not buffer.strip():
            break
        buffer += chunk
        while True:
            buffer = buffer.lstrip()
            if not started:
                if not buffer:
                    break
                if buffer[0] != "[":
                    value = json.loads(buffer)
                    if not isinstance(value, dict):
                        raise ValueError("JSON payload must be an object or array of objects")
                    yield value
                    return
                buffer = buffer[1:]
                started = True
            buffer = buffer.lstrip()
            if buffer.startswith("]"):
                finished = True
                break
            if buffer.startswith(","):
                buffer = buffer[1:].lstrip()
            try:
                value, offset = decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                if not chunk:
                    raise
                break
            if not isinstance(value, dict):
                raise ValueError("JSON array elements must be objects")
            yield value
            buffer = buffer[offset:]


def _parse_file(imported_file: ImportedFile, dataset_type: str) -> Iterator[dict[str, Any]]:
    if imported_file.content_type not in _ALLOWED_UPLOAD_CONTENT_TYPES:
        raise ValueError("Unsupported uploaded content type")
    path = _materialize_object(imported_file)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            if imported_file.original_filename.casefold().endswith(".csv"):
                for row in csv.DictReader(source):
                    yield {"entity_type": dataset_type, "payload": dict(row)}
                return
            if (
                imported_file.content_type == "application/x-ndjson"
                or imported_file.original_filename.casefold().endswith((".ndjson", ".jsonl"))
            ):
                for line in source:
                    if line.strip():
                        value = json.loads(line)
                        if not isinstance(value, dict):
                            raise ValueError("NDJSON lines must contain objects")
                        yield value
                return
            yield from _stream_json_array(source)
    finally:
        path.unlink(missing_ok=True)


def _normalize_input_record(
    document: Mapping[str, Any], dataset_type: str, row_number: int
) -> dict[str, Any]:
    payload_value = document.get("payload", document)
    if not isinstance(payload_value, Mapping):
        raise ValueError("Record payload must be an object")
    payload = dict(payload_value)
    entity_type = str(document.get("entity_type") or dataset_type)
    if entity_type == "all" or entity_type not in _ENTITY_ORDER:
        raise ValueError("Each mixed dataset record requires a supported entity_type")
    external_id = str(
        document.get("external_id")
        or payload.get("external_id")
        or payload.get("sku")
        or payload.get("supplier_code")
        or payload.get("sale_number")
        or payload.get("purchase_number")
        or f"row-{row_number}-{sha256(repr(sorted(payload.items())).encode()).hexdigest()[:16]}"
    )
    occurred_value = (
        document.get("occurred_at") or payload.get("occurred_at") or payload.get("valid_from")
    )
    try:
        occurred_at = (
            datetime.fromisoformat(str(occurred_value).replace("Z", "+00:00"))
            if occurred_value
            else datetime.now(UTC)
        )
    except ValueError:
        occurred_at = datetime.now(UTC)
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    payload.setdefault("occurred_at", str(occurred_value or occurred_at.isoformat()))
    return {
        "entity_type": entity_type,
        "external_id": external_id[:240],
        "source_version": str(
            document.get("source_version") or payload.get("source_version") or "1"
        )[:100],
        "occurred_at": occurred_at,
        "content_hash": str(
            document.get("content_hash")
            or sha256(repr(sorted(payload.items())).encode()).hexdigest()
        ),
        "page_number": int(document.get("page") or 1),
        "row_number": int(document.get("sequence") or row_number),
        "raw_payload": payload,
    }


async def _insert_staging_chunk(
    tenant_id: UUID,
    batch_id: UUID,
    source_id: UUID,
    rows: list[dict[str, Any]],
) -> int:
    session = await _tenant_session(tenant_id)
    try:
        values = [
            {
                "id": uuid4(),
                "tenant_id": tenant_id,
                "batch_id": batch_id,
                "data_source_id": source_id,
                "status": "received",
                "error_count": 0,
                **row,
            }
            for row in rows
        ]
        statement = (
            insert(StagingRecord)
            .values(values)
            .on_conflict_do_nothing(
                index_elements=[
                    "tenant_id",
                    "batch_id",
                    "entity_type",
                    "external_id",
                    "source_version",
                ]
            )
            .returning(StagingRecord.id)
        )
        inserted = len((await session.scalars(statement)).all())
        execution_id = await session.scalar(
            select(SyncExecution.id).where(SyncExecution.batch_id == batch_id)
        )
        if execution_id is not None:
            committed = int(
                await session.scalar(
                    select(func.count(StagingRecord.id)).where(StagingRecord.batch_id == batch_id)
                )
                or 0
            )
            checkpoint = insert(SyncCheckpoint).values(
                id=uuid5(execution_id, "checkpoint:parse"),
                tenant_id=tenant_id,
                execution_id=execution_id,
                step_name="parse",
                cursor_value=str(max(row["row_number"] for row in rows)),
                page_number=max(row["page_number"] for row in rows),
                records_committed=committed,
                source_version=str(rows[-1]["source_version"]),
            )
            await session.execute(
                checkpoint.on_conflict_do_update(
                    index_elements=["tenant_id", "execution_id", "step_name"],
                    set_={
                        "cursor_value": checkpoint.excluded.cursor_value,
                        "page_number": checkpoint.excluded.page_number,
                        "records_committed": checkpoint.excluded.records_committed,
                        "source_version": checkpoint.excluded.source_version,
                        "updated_at": func.now(),
                    },
                )
            )
        await session.commit()
        return inserted
    finally:
        await session.close()


async def _parse_batch(batch_id: UUID, tenant_id: UUID, correlation_id: str) -> None:
    session = await _tenant_session(tenant_id)
    try:
        batch = await session.scalar(
            select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update()
        )
        if batch is None or is_terminal_state(batch.state):
            return
        if batch.cancel_requested:
            await transition_batch(
                session, batch, ProcessingState.CANCELLED, actor_type="worker", actor_id="parse"
            )
            await session.commit()
            return
        if batch.state in {
            ProcessingState.RETRY_SCHEDULED.value,
            ProcessingState.QUEUED.value,
        }:
            await transition_batch(
                session, batch, ProcessingState.RECEIVED, actor_type="worker", actor_id="parse"
            )
        elif batch.state != ProcessingState.RECEIVED.value:
            return
        await _start_step(session, batch, "parse", ProcessingState.RECEIVED)
        manifest = await session.scalar(
            select(LandingManifest).where(LandingManifest.batch_id == batch.id)
        )
        if manifest is None:
            raise RuntimeError("Landing manifest not found")
        imported_file = await session.get(ImportedFile, manifest.imported_file_id)
        if imported_file is None:
            raise RuntimeError("Imported file not found")
        source_id = batch.data_source_id
        dataset_type = batch.dataset_type
        await session.commit()
    finally:
        await session.close()

    parse_started = perf_counter()
    total = 0
    inserted = 0
    chunk: list[dict[str, Any]] = []
    for total, document in enumerate(_parse_file(imported_file, dataset_type), start=1):
        chunk.append(_normalize_input_record(document, dataset_type, total))
        if len(chunk) >= get_settings().integration_chunk_records:
            inserted += await _insert_staging_chunk(tenant_id, batch_id, source_id, chunk)
            chunk.clear()
    if chunk:
        inserted += await _insert_staging_chunk(tenant_id, batch_id, source_id, chunk)

    session = await _tenant_session(tenant_id)
    try:
        batch = await session.scalar(
            select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update()
        )
        if batch is None:
            return
        batch.received_records = total
        batch.duplicate_records = total - inserted
        batch.progress_percent = 30
        await transition_batch(
            session,
            batch,
            ProcessingState.VALIDATING,
            actor_type="worker",
            actor_id="parse",
        )
        active_step = await session.scalar(
            select(ProcessingStep)
            .where(ProcessingStep.batch_id == batch.id, ProcessingStep.step_name == "parse")
            .order_by(ProcessingStep.attempt_number.desc())
        )
        if active_step:
            _finish_step(active_step, ProcessingState.VALIDATING)
        duration_ms = max(1, int((perf_counter() - parse_started) * 1_000))
        session.add(
            ProcessingStatistic(
                tenant_id=tenant_id,
                batch_id=batch.id,
                step_name="parse",
                entity_type="all",
                received_count=total,
                valid_count=inserted,
                rejected_count=0,
                duplicate_count=total - inserted,
                bytes_received=imported_file.size_bytes,
                duration_ms=duration_ms,
                records_per_second=Decimal(total * 1_000) / Decimal(duration_ms),
            )
        )
        await session.commit()
    finally:
        await session.close()
    validate_batch.send(str(batch_id), str(tenant_id), correlation_id)


@dramatiq.actor(
    queue_name="integration-process",
    max_retries=5,
    min_backoff=2_000,
    max_backoff=120_000,
    time_limit=900_000,
)
def parse_batch(batch_id: str, tenant_id: str, correlation_id: str = "") -> None:
    try:
        _run(_parse_batch(UUID(batch_id), UUID(tenant_id), correlation_id))
    except Exception as exc:
        _actor_failure(batch_id, tenant_id, "parse", exc)
        raise


async def _validate_batch(batch_id: UUID, tenant_id: UUID, correlation_id: str) -> None:
    session = await _tenant_session(tenant_id)
    try:
        batch = await session.scalar(
            select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update()
        )
        if batch is None or is_terminal_state(batch.state):
            return
        if batch.cancel_requested:
            await transition_batch(
                session,
                batch,
                ProcessingState.CANCELLED,
                actor_type="worker",
                actor_id="validate",
            )
            await session.commit()
            return
        if batch.state == ProcessingState.RETRY_SCHEDULED.value:
            await transition_batch(
                session,
                batch,
                ProcessingState.VALIDATING,
                actor_type="worker",
                actor_id="validate",
            )
        elif batch.state != ProcessingState.VALIDATING.value:
            return
        step = await _start_step(session, batch, "validate", ProcessingState.VALIDATING)
        records = (
            await session.scalars(
                select(StagingRecord)
                .where(StagingRecord.batch_id == batch.id)
                .order_by(StagingRecord.row_number)
            )
        ).all()
        context = QualityContext(branch_exists=batch.branch_id is not None)
        context.known_products.update(
            str(record.raw_payload.get("sku"))
            for record in records
            if record.entity_type == "product" and record.raw_payload.get("sku")
        )
        context.known_suppliers.update(
            str(record.raw_payload.get("supplier_code"))
            for record in records
            if record.entity_type == "supplier" and record.raw_payload.get("supplier_code")
        )
        context.known_products.update(
            (
                await session.scalars(
                    select(Product.external_id).where(Product.company_id == batch.company_id)
                )
            ).all()
        )
        context.known_suppliers.update(
            (
                await session.scalars(
                    select(Supplier.external_id).where(Supplier.company_id == batch.company_id)
                )
            ).all()
        )
        rule_entity_counts: Counter[tuple[str, str, str]] = Counter()
        entity_quality_failures: Counter[str] = Counter()
        rejected = 0
        valid = 0
        for record in records:
            findings = quality_engine.evaluate_record(
                record.entity_type,
                record.external_id,
                record.raw_payload,
                context,
            )
            blocking = [finding for finding in findings if finding.blocks_loading]
            if findings:
                entity_quality_failures[record.entity_type] += 1
            record.error_count = len(findings)
            record.normalized_payload = dict(record.raw_payload)
            record.status = "rejected" if blocking else "valid"
            rejected += bool(blocking)
            valid += not blocking
            for finding in findings:
                rule_entity_counts[
                    (finding.entity_type, finding.rule_key, finding.severity.value)
                ] += 1
                session.add(
                    ProcessingError(
                        tenant_id=tenant_id,
                        batch_id=batch.id,
                        staging_record_id=record.id,
                        step_name="validate",
                        entity_type=record.entity_type,
                        field_name=finding.field_name,
                        error_class="data_quality",
                        error_code=finding.rule_type.value,
                        severity=finding.severity.value,
                        message=finding.message,
                        retryable=False,
                    )
                )
            if blocking:
                session.add(
                    RejectedRecord(
                        tenant_id=tenant_id,
                        batch_id=batch.id,
                        staging_record_id=record.id,
                        entity_type=record.entity_type,
                        reason_code=blocking[0].rule_type.value,
                        status="open",
                    )
                )
        await session.execute(delete(QualityResult).where(QualityResult.batch_id == batch.id))
        entity_totals = Counter(record.entity_type for record in records)
        for entity, evaluated in entity_totals.items():
            failed = entity_quality_failures[entity]
            score = Decimal(evaluated - failed) / Decimal(evaluated) * 100
            session.add(
                QualityResult(
                    tenant_id=tenant_id,
                    batch_id=batch.id,
                    entity_type=entity,
                    rule_key="platform.overall",
                    severity="informational",
                    evaluated_records=evaluated,
                    failed_records=failed,
                    score=score,
                    details={"correlation_id": correlation_id, "summary": True},
                )
            )
        for (entity, rule_key, severity), failed in rule_entity_counts.items():
            evaluated = entity_totals[entity]
            score = (
                (Decimal(evaluated - failed) / Decimal(evaluated) * 100)
                if evaluated
                else Decimal(100)
            )
            session.add(
                QualityResult(
                    tenant_id=tenant_id,
                    batch_id=batch.id,
                    entity_type=entity,
                    rule_key=rule_key,
                    severity=severity,
                    evaluated_records=evaluated,
                    failed_records=failed,
                    score=score,
                    details={"correlation_id": correlation_id},
                )
            )
        batch.valid_records = valid
        batch.rejected_records = rejected
        batch.progress_percent = 50
        await transition_batch(
            session,
            batch,
            ProcessingState.MAPPING,
            actor_type="worker",
            actor_id="validate",
        )
        _finish_step(step, ProcessingState.MAPPING)
        await session.commit()
    finally:
        await session.close()
    map_batch.send(str(batch_id), str(tenant_id), correlation_id)


@dramatiq.actor(
    queue_name="integration-process",
    max_retries=5,
    min_backoff=2_000,
    max_backoff=120_000,
    time_limit=900_000,
)
def validate_batch(batch_id: str, tenant_id: str, correlation_id: str = "") -> None:
    try:
        _run(_validate_batch(UUID(batch_id), UUID(tenant_id), correlation_id))
    except Exception as exc:
        _actor_failure(batch_id, tenant_id, "validate", exc)
        raise


def _transform(value: Any, mapping: FieldMapping) -> Any:
    if value is None:
        value = mapping.default_value
    transform = mapping.transform_type
    if transform == "identity":
        return value
    if transform == "constant":
        return mapping.transform_config.get("value", mapping.default_value)
    if value is None:
        return None
    if transform == "trim":
        return str(value).strip()
    if transform == "uppercase":
        return str(value).upper()
    if transform == "lowercase":
        return str(value).lower()
    if transform == "decimal":
        return str(Decimal(str(value).replace(",", ".")))
    if transform == "integer":
        return int(value)
    if transform in {"date", "datetime"}:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).isoformat()
    if transform == "boolean":
        return str(value).casefold() in {"1", "true", "yes", "sim"}
    raise ValueError(f"Unsupported mapping transform: {transform}")


async def _map_batch(batch_id: UUID, tenant_id: UUID, correlation_id: str) -> None:
    session = await _tenant_session(tenant_id)
    try:
        batch = await session.scalar(
            select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update()
        )
        if batch is None or is_terminal_state(batch.state):
            return
        if batch.state == ProcessingState.RETRY_SCHEDULED.value:
            await transition_batch(
                session, batch, ProcessingState.MAPPING, actor_type="worker", actor_id="map"
            )
        elif batch.state != ProcessingState.MAPPING.value:
            return
        step = await _start_step(session, batch, "map", ProcessingState.MAPPING)
        mappings: list[FieldMapping] = []
        if batch.mapping_version_id is not None:
            mappings = list(
                (
                    await session.scalars(
                        select(FieldMapping).where(
                            FieldMapping.mapping_version_id == batch.mapping_version_id
                        )
                    )
                ).all()
            )
        records = (
            await session.scalars(
                select(StagingRecord).where(
                    StagingRecord.batch_id == batch.id,
                    StagingRecord.status == "valid",
                )
            )
        ).all()
        for record in records:
            relevant = [
                mapping for mapping in mappings if mapping.target_entity == record.entity_type
            ]
            if not relevant:
                record.normalized_payload = dict(record.raw_payload)
                continue
            mapped: dict[str, Any] = {}
            for mapping in relevant:
                value = record.raw_payload.get(mapping.source_field)
                if (
                    mapping.required
                    and (value is None or value == "")
                    and mapping.default_value is None
                ):
                    raise ValueError(
                        f"Required mapped source field missing: {mapping.source_field}"
                    )
                mapped[mapping.target_field] = _transform(value, mapping)
            record.normalized_payload = mapped
        batch.progress_percent = 60
        await transition_batch(
            session,
            batch,
            ProcessingState.NORMALIZING,
            actor_type="worker",
            actor_id="map",
        )
        _finish_step(step, ProcessingState.NORMALIZING)
        await session.commit()
    finally:
        await session.close()
    normalize_batch.send(str(batch_id), str(tenant_id), correlation_id)


@dramatiq.actor(
    queue_name="integration-process", max_retries=5, min_backoff=2_000, max_backoff=120_000
)
def map_batch(batch_id: str, tenant_id: str, correlation_id: str = "") -> None:
    try:
        _run(_map_batch(UUID(batch_id), UUID(tenant_id), correlation_id))
    except Exception as exc:
        _actor_failure(batch_id, tenant_id, "map", exc)
        raise


async def _normalize_batch(batch_id: UUID, tenant_id: UUID, correlation_id: str) -> None:
    session = await _tenant_session(tenant_id)
    try:
        batch = await session.scalar(
            select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update()
        )
        if batch is None or is_terminal_state(batch.state):
            return
        if batch.state == ProcessingState.RETRY_SCHEDULED.value:
            await transition_batch(
                session,
                batch,
                ProcessingState.NORMALIZING,
                actor_type="worker",
                actor_id="normalize",
            )
        elif batch.state != ProcessingState.NORMALIZING.value:
            return
        step = await _start_step(session, batch, "normalize", ProcessingState.NORMALIZING)
        records = (
            await session.scalars(
                select(StagingRecord).where(
                    StagingRecord.batch_id == batch.id,
                    StagingRecord.status == "valid",
                )
            )
        ).all()
        for record in records:
            normalized = dict(record.normalized_payload or record.raw_payload)
            for key, value in tuple(normalized.items()):
                if isinstance(value, str):
                    normalized[key] = value.strip()
            record.normalized_payload = normalized
        batch.progress_percent = 70
        await transition_batch(
            session,
            batch,
            ProcessingState.LOADING,
            actor_type="worker",
            actor_id="normalize",
        )
        _finish_step(step, ProcessingState.LOADING)
        await session.commit()
    finally:
        await session.close()
    load_batch.send(str(batch_id), str(tenant_id), correlation_id)


@dramatiq.actor(
    queue_name="integration-process", max_retries=5, min_backoff=2_000, max_backoff=120_000
)
def normalize_batch(batch_id: str, tenant_id: str, correlation_id: str = "") -> None:
    try:
        _run(_normalize_batch(UUID(batch_id), UUID(tenant_id), correlation_id))
    except Exception as exc:
        _actor_failure(batch_id, tenant_id, "normalize", exc)
        raise


def _stable_id(tenant_id: UUID, data_source_id: UUID, entity: str, external_id: str) -> UUID:
    return uuid5(tenant_id, f"{data_source_id}:{entity}:{external_id}")


def _decimal(value: Any, default: str = "0") -> Decimal:
    return Decimal(str(default if value in {None, ""} else value))


def _datetime(value: Any, fallback: datetime) -> datetime:
    if value in {None, ""}:
        return fallback
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or UTC)


def _date(value: Any) -> date | None:
    if value in {None, ""}:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


async def _upsert_named_dimension(
    session: AsyncSession,
    model: type[Brand] | type[Manufacturer] | type[Category],
    tenant_id: UUID,
    name: Any,
) -> UUID | None:
    cleaned = str(name or "").strip()
    if not cleaned:
        return None
    normalized = cleaned.casefold()
    dimension_id = uuid5(tenant_id, f"{model.__tablename__}:{normalized}")
    values: dict[str, Any] = {
        "id": dimension_id,
        "tenant_id": tenant_id,
        "name": cleaned,
        "normalized_name": normalized,
    }
    if model is Category:
        values.update(parent_id=None, level=0)
    statement = insert(model).values(**values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["id"],
            set_={"name": statement.excluded.name, "updated_at": func.now()},
        )
    )
    return dimension_id


async def _load_product(
    session: AsyncSession, batch: ImportBatch, record: StagingRecord, payload: Mapping[str, Any]
) -> UUID:
    product_id = _stable_id(batch.tenant_id, batch.data_source_id, "product", record.external_id)
    brand_id = await _upsert_named_dimension(session, Brand, batch.tenant_id, payload.get("brand"))
    manufacturer_id = await _upsert_named_dimension(
        session, Manufacturer, batch.tenant_id, payload.get("manufacturer")
    )
    category_id = await _upsert_named_dimension(
        session, Category, batch.tenant_id, payload.get("category")
    )
    name = str(payload.get("name") or record.external_id).strip()
    values = {
        "id": product_id,
        "tenant_id": batch.tenant_id,
        "company_id": batch.company_id,
        "branch_id": batch.branch_id,
        "data_source_id": batch.data_source_id,
        "batch_id": batch.id,
        "staging_record_id": record.id,
        "external_id": record.external_id,
        "source_version": record.source_version,
        "sku": str(payload.get("sku") or record.external_id),
        "name": name,
        "normalized_name": name.casefold(),
        "brand_id": brand_id,
        "manufacturer_id": manufacturer_id,
        "category_id": category_id,
        "base_unit": str(payload.get("unit") or "UN")[:24],
        "commercial_status": str(payload.get("commercial_status") or "active")[:24],
        "commercial_classification": payload.get("commercial_classification"),
        "regulatory_metadata": dict(payload.get("regulatory_metadata") or {}),
        "controlled_attributes": dict(payload.get("controlled_attributes") or {}),
    }
    statement = insert(Product).values(**values)
    mutable = {
        key: getattr(statement.excluded, key) for key in values if key not in {"id", "tenant_id"}
    }
    mutable["updated_at"] = func.now()
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["tenant_id", "data_source_id", "external_id"], set_=mutable
        )
    )
    identifiers = (("sku", payload.get("sku")), ("ean", payload.get("ean")))
    for identifier_type, identifier_value in identifiers:
        if not identifier_value:
            continue
        identifier = insert(ProductIdentifier).values(
            id=uuid5(batch.tenant_id, f"product-identifier:{identifier_type}:{identifier_value}"),
            tenant_id=batch.tenant_id,
            product_id=product_id,
            data_source_id=batch.data_source_id,
            identifier_type=identifier_type,
            identifier_value=str(identifier_value),
            primary=identifier_type == "sku",
        )
        await session.execute(
            identifier.on_conflict_do_update(
                index_elements=["tenant_id", "identifier_type", "identifier_value"],
                set_={"product_id": product_id, "data_source_id": batch.data_source_id},
            )
        )
    presentation_name = str(payload.get("presentation") or "unidade")
    presentation = insert(ProductPresentation).values(
        id=uuid5(product_id, f"presentation:{presentation_name.casefold()}"),
        tenant_id=batch.tenant_id,
        product_id=product_id,
        name=presentation_name,
        unit=str(payload.get("unit") or "UN")[:24],
        conversion_factor=_decimal(payload.get("conversion_factor"), "1"),
        barcode=payload.get("ean"),
    )
    await session.execute(
        presentation.on_conflict_do_update(
            index_elements=["tenant_id", "product_id", "name"],
            set_={
                "unit": presentation.excluded.unit,
                "conversion_factor": presentation.excluded.conversion_factor,
                "barcode": presentation.excluded.barcode,
                "updated_at": func.now(),
            },
        )
    )
    return product_id


async def _load_supplier(
    session: AsyncSession, batch: ImportBatch, record: StagingRecord, payload: Mapping[str, Any]
) -> UUID:
    supplier_id = _stable_id(batch.tenant_id, batch.data_source_id, "supplier", record.external_id)
    name = str(payload.get("name") or record.external_id).strip()
    values = {
        "id": supplier_id,
        "tenant_id": batch.tenant_id,
        "company_id": batch.company_id,
        "data_source_id": batch.data_source_id,
        "batch_id": batch.id,
        "staging_record_id": record.id,
        "external_id": record.external_id,
        "source_version": record.source_version,
        "name": name,
        "normalized_name": name.casefold(),
        "tax_id_hash": payload.get("tax_id_hash"),
        "status": str(payload.get("status") or "active")[:24],
        "commercial_terms": {
            "lead_time_days": payload.get("lead_time_days"),
            "minimum_order": payload.get("minimum_order"),
        },
    }
    statement = insert(Supplier).values(**values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["tenant_id", "data_source_id", "external_id"],
            set_={
                key: getattr(statement.excluded, key)
                for key in values
                if key not in {"id", "tenant_id"}
            }
            | {"updated_at": func.now()},
        )
    )
    code = str(payload.get("supplier_code") or record.external_id)
    identifier = insert(SupplierIdentifier).values(
        id=uuid5(batch.tenant_id, f"supplier-identifier:source:{code}"),
        tenant_id=batch.tenant_id,
        supplier_id=supplier_id,
        identifier_type="source",
        identifier_value=code,
    )
    await session.execute(
        identifier.on_conflict_do_update(
            index_elements=["tenant_id", "identifier_type", "identifier_value"],
            set_={"supplier_id": supplier_id},
        )
    )
    return supplier_id


def _require_branch(batch: ImportBatch, entity: str) -> UUID:
    if batch.branch_id is None:
        raise ValueError(f"A branch-scoped data source is required to load {entity}")
    return batch.branch_id


async def _load_sale(
    session: AsyncSession, batch: ImportBatch, record: StagingRecord, payload: Mapping[str, Any]
) -> UUID:
    branch_id = _require_branch(batch, "sales")
    sale_id = _stable_id(batch.tenant_id, batch.data_source_id, "sale", record.external_id)
    occurred_at = _datetime(payload.get("occurred_at"), record.occurred_at)
    values = {
        "id": sale_id,
        "occurred_at": occurred_at,
        "tenant_id": batch.tenant_id,
        "company_id": batch.company_id,
        "branch_id": branch_id,
        "data_source_id": batch.data_source_id,
        "batch_id": batch.id,
        "staging_record_id": record.id,
        "external_id": record.external_id,
        "source_version": record.source_version,
        "accounting_at": _datetime(payload.get("accounting_at"), occurred_at),
        "channel": str(payload.get("channel") or "unknown")[:40],
        "status": str(payload.get("status") or "completed")[:24],
        "operator_external_id": payload.get("operator_id"),
        "customer_pseudonym": payload.get("customer_key"),
        "gross_total": _decimal(payload.get("gross_total")),
        "discount_total": _decimal(payload.get("discount_total")),
        "tax_total": _decimal(payload.get("tax_total")),
        "net_total": _decimal(payload.get("net_total")),
    }
    statement = insert(Sale).values(**values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["tenant_id", "data_source_id", "external_id", "occurred_at"],
            set_={
                key: getattr(statement.excluded, key)
                for key in values
                if key not in {"id", "occurred_at", "tenant_id", "data_source_id", "external_id"}
            }
            | {"updated_at": func.now()},
        )
    )
    await session.execute(
        delete(SaleItem).where(
            SaleItem.tenant_id == batch.tenant_id,
            SaleItem.sale_id == sale_id,
            SaleItem.sale_occurred_at == occurred_at,
        )
    )
    await session.execute(
        delete(SalePayment).where(
            SalePayment.tenant_id == batch.tenant_id,
            SalePayment.sale_id == sale_id,
            SalePayment.sale_occurred_at == occurred_at,
        )
    )
    await session.execute(
        delete(SaleAdjustment).where(
            SaleAdjustment.tenant_id == batch.tenant_id,
            SaleAdjustment.sale_id == sale_id,
            SaleAdjustment.sale_occurred_at == occurred_at,
        )
    )
    for index, item in enumerate(payload.get("items") or (), start=1):
        line = int(item.get("line") or index)
        product_code = str(item.get("product_code") or "")
        product_id = _stable_id(batch.tenant_id, batch.data_source_id, "product", product_code)
        quantity = _decimal(item.get("quantity"))
        unit_price = _decimal(item.get("unit_price"))
        session.add(
            SaleItem(
                id=uuid5(sale_id, f"item:{line}"),
                tenant_id=batch.tenant_id,
                sale_id=sale_id,
                sale_occurred_at=occurred_at,
                product_id=product_id,
                line_number=line,
                quantity=quantity,
                unit_price=unit_price,
                unit_cost=_decimal(item.get("unit_cost"))
                if item.get("unit_cost") is not None
                else None,
                gross_total=_decimal(item.get("gross_total"), str(quantity * unit_price)),
                discount_total=_decimal(item.get("discount_total")),
                tax_total=_decimal(item.get("tax_total")),
                net_total=_decimal(item.get("net_total"), str(quantity * unit_price)),
            )
        )
    for index, payment in enumerate(payload.get("payments") or (), start=1):
        session.add(
            SalePayment(
                id=uuid5(sale_id, f"payment:{index}"),
                tenant_id=batch.tenant_id,
                sale_id=sale_id,
                sale_occurred_at=occurred_at,
                method=str(payment.get("method") or "unknown")[:60],
                amount=_decimal(payment.get("amount")),
                installments=int(payment.get("installments") or 1),
            )
        )
    for index, adjustment in enumerate(payload.get("adjustments") or (), start=1):
        session.add(
            SaleAdjustment(
                id=uuid5(sale_id, f"adjustment:{index}"),
                tenant_id=batch.tenant_id,
                sale_id=sale_id,
                sale_occurred_at=occurred_at,
                adjustment_type=str(adjustment.get("type") or "discount")[:24],
                amount=_decimal(adjustment.get("amount")),
                reason=adjustment.get("reason"),
                occurred_at=_datetime(adjustment.get("occurred_at"), occurred_at),
            )
        )
    return sale_id


async def _load_purchase(
    session: AsyncSession, batch: ImportBatch, record: StagingRecord, payload: Mapping[str, Any]
) -> UUID:
    branch_id = _require_branch(batch, "purchases")
    purchase_id = _stable_id(batch.tenant_id, batch.data_source_id, "purchase", record.external_id)
    supplier_code = str(payload.get("supplier_code") or "")
    supplier_id = _stable_id(batch.tenant_id, batch.data_source_id, "supplier", supplier_code)
    ordered_at = _datetime(
        payload.get("ordered_at") or payload.get("occurred_at"), record.occurred_at
    )
    items = list(payload.get("items") or ())
    merchandise_total = sum((_decimal(item.get("net_total")) for item in items), Decimal())
    values = {
        "id": purchase_id,
        "tenant_id": batch.tenant_id,
        "company_id": batch.company_id,
        "branch_id": branch_id,
        "supplier_id": supplier_id,
        "data_source_id": batch.data_source_id,
        "batch_id": batch.id,
        "staging_record_id": record.id,
        "external_id": record.external_id,
        "source_version": record.source_version,
        "status": str(payload.get("status") or "received")[:24],
        "ordered_at": ordered_at,
        "issued_at": _datetime(payload.get("issued_at"), ordered_at),
        "accounting_at": _datetime(payload.get("accounting_at"), ordered_at),
        "expected_at": _datetime(payload.get("expected_at"), ordered_at),
        "merchandise_total": merchandise_total,
        "discount_total": _decimal(payload.get("discount_total")),
        "bonus_total": _decimal(payload.get("bonus_total")),
        "freight_total": _decimal(payload.get("freight_total")),
        "tax_total": _decimal(payload.get("tax_total")),
        "net_total": _decimal(
            payload.get("net_total"),
            str(
                merchandise_total
                + _decimal(payload.get("freight_total"))
                + _decimal(payload.get("tax_total"))
            ),
        ),
    }
    statement = insert(PurchaseOrder).values(**values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["tenant_id", "data_source_id", "external_id"],
            set_={
                key: getattr(statement.excluded, key)
                for key in values
                if key not in {"id", "tenant_id", "data_source_id", "external_id"}
            }
            | {"updated_at": func.now()},
        )
    )
    await session.execute(
        delete(PurchaseItem).where(
            PurchaseItem.tenant_id == batch.tenant_id,
            PurchaseItem.purchase_order_id == purchase_id,
        )
    )
    for index, item in enumerate(items, start=1):
        line = int(item.get("line") or index)
        product_id = _stable_id(
            batch.tenant_id,
            batch.data_source_id,
            "product",
            str(item.get("product_code") or ""),
        )
        unit_cost = _decimal(item.get("unit_cost"))
        session.add(
            PurchaseItem(
                id=uuid5(purchase_id, f"item:{line}"),
                tenant_id=batch.tenant_id,
                purchase_order_id=purchase_id,
                product_id=product_id,
                line_number=line,
                quantity=_decimal(item.get("quantity")),
                unit_cost=unit_cost,
                discount_total=_decimal(item.get("discount_total")),
                bonus_quantity=_decimal(item.get("bonus_quantity")),
                tax_total=_decimal(item.get("tax_total")),
                net_total=_decimal(item.get("net_total")),
            )
        )
        supplier_product_id = uuid5(supplier_id, f"product:{product_id}")
        supplier_product = insert(SupplierProduct).values(
            id=supplier_product_id,
            tenant_id=batch.tenant_id,
            supplier_id=supplier_id,
            product_id=product_id,
            supplier_product_code=item.get("supplier_product_code"),
            lead_time_days=max(0, int(item.get("lead_time_days") or 0)),
            minimum_order=_decimal(item.get("minimum_order")),
            purchase_multiple=_decimal(item.get("purchase_multiple"), "1"),
            current_cost=unit_cost,
        )
        await session.execute(
            supplier_product.on_conflict_do_update(
                index_elements=["tenant_id", "supplier_id", "product_id"],
                set_={
                    "current_cost": unit_cost,
                    "supplier_product_code": supplier_product.excluded.supplier_product_code,
                    "updated_at": func.now(),
                },
            )
        )
        cost = insert(SupplierCost).values(
            id=uuid5(record.id, f"supplier-cost:{line}"),
            tenant_id=batch.tenant_id,
            supplier_product_id=supplier_product_id,
            cost=unit_cost,
            valid_from=ordered_at,
            valid_to=None,
            batch_id=batch.id,
        )
        await session.execute(cost.on_conflict_do_nothing(index_elements=["id"]))
    receipt_number = str(payload.get("document_number") or record.external_id)
    receipt = insert(PurchaseReceipt).values(
        id=uuid5(purchase_id, f"receipt:{receipt_number}"),
        tenant_id=batch.tenant_id,
        purchase_order_id=purchase_id,
        document_type="receipt",
        document_number=receipt_number,
        issued_at=ordered_at,
        received_at=_datetime(payload.get("received_at"), ordered_at),
        total=values["net_total"],
    )
    await session.execute(
        receipt.on_conflict_do_update(
            index_elements=["tenant_id", "purchase_order_id", "document_number"],
            set_={"received_at": receipt.excluded.received_at, "total": receipt.excluded.total},
        )
    )
    return purchase_id


async def _load_stock(
    session: AsyncSession, batch: ImportBatch, record: StagingRecord, payload: Mapping[str, Any]
) -> UUID:
    branch_id = _require_branch(batch, "inventory")
    product_code = str(payload.get("product_code") or "")
    product_id = _stable_id(batch.tenant_id, batch.data_source_id, "product", product_code)
    occurred_at = _datetime(payload.get("occurred_at"), record.occurred_at)
    lot_id: UUID | None = None
    if payload.get("lot_number"):
        lot_id = uuid5(branch_id, f"lot:{product_id}:{payload['lot_number']}")
        lot = insert(InventoryLot).values(
            id=lot_id,
            tenant_id=batch.tenant_id,
            company_id=batch.company_id,
            branch_id=branch_id,
            product_id=product_id,
            lot_number=str(payload["lot_number"]),
            manufactured_on=_date(payload.get("manufactured_on")),
            expires_on=_date(payload.get("expires_on")),
            quantity=_decimal(payload.get("on_hand")),
        )
        await session.execute(
            lot.on_conflict_do_update(
                index_elements=["tenant_id", "branch_id", "product_id", "lot_number"],
                set_={
                    "expires_on": lot.excluded.expires_on,
                    "quantity": lot.excluded.quantity,
                    "updated_at": func.now(),
                },
            )
        )
    balance_id = uuid5(branch_id, f"balance:{product_id}")
    balance_values = {
        "id": balance_id,
        "tenant_id": batch.tenant_id,
        "company_id": batch.company_id,
        "branch_id": branch_id,
        "product_id": product_id,
        "data_source_id": batch.data_source_id,
        "batch_id": batch.id,
        "staging_record_id": record.id,
        "source_version": record.source_version,
        "on_hand": _decimal(payload.get("on_hand")),
        "reserved": _decimal(payload.get("reserved")),
        "in_transit": _decimal(payload.get("in_transit")),
        "updated_from_source_at": occurred_at,
    }
    balance = insert(StockBalance).values(**balance_values)
    await session.execute(
        balance.on_conflict_do_update(
            index_elements=["tenant_id", "branch_id", "product_id"],
            set_={
                key: getattr(balance.excluded, key)
                for key in balance_values
                if key not in {"id", "tenant_id", "branch_id", "product_id"}
            }
            | {"updated_at": func.now()},
        )
    )
    snapshot_id = uuid5(record.id, "stock-snapshot")
    snapshot = insert(StockSnapshot).values(
        id=snapshot_id,
        tenant_id=batch.tenant_id,
        company_id=batch.company_id,
        branch_id=branch_id,
        product_id=product_id,
        batch_id=batch.id,
        snapshot_at=occurred_at,
        on_hand=balance_values["on_hand"],
        reserved=balance_values["reserved"],
        in_transit=balance_values["in_transit"],
    )
    await session.execute(snapshot.on_conflict_do_nothing(index_elements=["id"]))
    movement_id = _stable_id(batch.tenant_id, batch.data_source_id, "movement", record.external_id)
    movement = insert(InventoryMovement).values(
        id=movement_id,
        tenant_id=batch.tenant_id,
        company_id=batch.company_id,
        branch_id=branch_id,
        product_id=product_id,
        inventory_lot_id=lot_id,
        data_source_id=batch.data_source_id,
        batch_id=batch.id,
        staging_record_id=record.id,
        external_id=record.external_id,
        source_version=record.source_version,
        movement_type=str(payload.get("movement_type") or "inventory")[:24],
        quantity=_decimal(payload.get("movement_quantity"), "1"),
        balance_after=balance_values["on_hand"],
        occurred_at=occurred_at,
        accounting_at=_datetime(payload.get("accounting_at"), occurred_at),
        reference_type="import_batch",
        reference_id=str(batch.id),
    )
    await session.execute(
        movement.on_conflict_do_update(
            index_elements=["tenant_id", "data_source_id", "external_id"],
            set_={
                "quantity": movement.excluded.quantity,
                "balance_after": movement.excluded.balance_after,
                "batch_id": batch.id,
                "staging_record_id": record.id,
            },
        )
    )
    return balance_id


async def _load_price(
    session: AsyncSession, batch: ImportBatch, record: StagingRecord, payload: Mapping[str, Any]
) -> UUID:
    branch_id = _require_branch(batch, "prices")
    product_id = _stable_id(
        batch.tenant_id, batch.data_source_id, "product", str(payload.get("product_code") or "")
    )
    valid_from = _datetime(payload.get("valid_from"), record.occurred_at)
    price_id = uuid5(record.id, f"price:{valid_from.isoformat()}")
    await session.execute(
        update(ProductPrice)
        .where(
            ProductPrice.tenant_id == batch.tenant_id,
            ProductPrice.branch_id == branch_id,
            ProductPrice.product_id == product_id,
            ProductPrice.current.is_(True),
            ProductPrice.valid_from < valid_from,
        )
        .values(current=False, valid_to=valid_from)
    )
    price = insert(ProductPrice).values(
        id=price_id,
        tenant_id=batch.tenant_id,
        company_id=batch.company_id,
        branch_id=branch_id,
        product_id=product_id,
        data_source_id=batch.data_source_id,
        batch_id=batch.id,
        staging_record_id=record.id,
        external_id=record.external_id,
        source_version=record.source_version,
        price=_decimal(payload.get("price")),
        reference_price=(
            _decimal(payload.get("reference_price"))
            if payload.get("reference_price") is not None
            else None
        ),
        reference_cost=(
            _decimal(payload.get("reference_cost"))
            if payload.get("reference_cost") is not None
            else None
        ),
        decision_source=str(payload.get("decision_source") or "erp")[:60],
        valid_from=valid_from,
        valid_to=None,
        current=True,
    )
    await session.execute(
        price.on_conflict_do_update(
            index_elements=["tenant_id", "data_source_id", "external_id", "valid_from"],
            set_={
                "price": price.excluded.price,
                "reference_price": price.excluded.reference_price,
                "reference_cost": price.excluded.reference_cost,
                "batch_id": batch.id,
                "staging_record_id": record.id,
                "current": True,
                "updated_at": func.now(),
            },
        )
    )
    if payload.get("promotion"):
        valid_to = _datetime(payload.get("promotion_valid_to"), valid_from + timedelta(days=7))
        promotion_id = _stable_id(
            batch.tenant_id, batch.data_source_id, "promotion", record.external_id
        )
        promotion = insert(Promotion).values(
            id=promotion_id,
            tenant_id=batch.tenant_id,
            company_id=batch.company_id,
            branch_id=branch_id,
            data_source_id=batch.data_source_id,
            batch_id=batch.id,
            external_id=record.external_id,
            source_version=record.source_version,
            name=str(payload.get("promotion_name") or f"Promoção {record.external_id}"),
            discount_type=str(payload.get("discount_type") or "percentage")[:24],
            discount_value=_decimal(payload.get("discount_value")),
            conditions=dict(payload.get("promotion_conditions") or {}),
            decision_source=str(payload.get("decision_source") or "erp")[:60],
            valid_from=valid_from,
            valid_to=valid_to,
            active=True,
        )
        await session.execute(
            promotion.on_conflict_do_update(
                index_elements=["tenant_id", "data_source_id", "external_id"],
                set_={
                    "batch_id": batch.id,
                    "discount_value": promotion.excluded.discount_value,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                    "active": True,
                    "updated_at": func.now(),
                },
            )
        )
        link = insert(PromotionProduct).values(
            id=uuid5(promotion_id, f"product:{product_id}"),
            tenant_id=batch.tenant_id,
            promotion_id=promotion_id,
            product_id=product_id,
            promotional_price=(
                _decimal(payload.get("promotional_price"))
                if payload.get("promotional_price") is not None
                else None
            ),
        )
        await session.execute(
            link.on_conflict_do_update(
                index_elements=["tenant_id", "promotion_id", "product_id"],
                set_={"promotional_price": link.excluded.promotional_price},
            )
        )
    return price_id


_CANONICAL_LOADERS = {
    "product": _load_product,
    "supplier": _load_supplier,
    "sale": _load_sale,
    "purchase": _load_purchase,
    "stock": _load_stock,
    "price": _load_price,
}


async def _load_batch(batch_id: UUID, tenant_id: UUID, correlation_id: str) -> None:
    session = await _tenant_session(tenant_id)
    try:
        batch = await session.scalar(
            select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update()
        )
        if batch is None or is_terminal_state(batch.state):
            return
        if batch.state == ProcessingState.RETRY_SCHEDULED.value:
            await transition_batch(
                session, batch, ProcessingState.LOADING, actor_type="worker", actor_id="load"
            )
        elif batch.state != ProcessingState.LOADING.value:
            return
        if batch.cancel_requested:
            await transition_batch(
                session, batch, ProcessingState.CANCELLED, actor_type="worker", actor_id="load"
            )
            await session.commit()
            return
        step = await _start_step(session, batch, "load", ProcessingState.LOADING)
        load_started = perf_counter()
        records = list(
            (
                await session.scalars(
                    select(StagingRecord)
                    .where(
                        StagingRecord.batch_id == batch.id,
                        StagingRecord.status == "valid",
                    )
                    .order_by(StagingRecord.row_number)
                )
            ).all()
        )
        records.sort(key=lambda item: (_ENTITY_ORDER.get(item.entity_type, 99), item.row_number))
        loaded = Counter[str]()
        for record in records:
            loader = _CANONICAL_LOADERS.get(record.entity_type)
            if loader is None:
                raise ValueError(f"Unsupported canonical entity: {record.entity_type}")
            target_id = await loader(
                session, batch, record, record.normalized_payload or record.raw_payload
            )
            session.add(
                LineageEvent(
                    id=uuid5(record.id, f"lineage:{record.entity_type}:{target_id}"),
                    tenant_id=batch.tenant_id,
                    batch_id=batch.id,
                    staging_record_id=record.id,
                    source_entity=record.entity_type,
                    source_external_id=record.external_id,
                    source_version=record.source_version,
                    target_entity=record.entity_type,
                    target_record_id=str(target_id),
                    operation="upsert",
                    created_at=datetime.now(UTC),
                )
            )
            record.status = "loaded"
            loaded[record.entity_type] += 1
        duration_ms = max(1, int((perf_counter() - load_started) * 1_000))
        for entity_type, count in loaded.items():
            statistic = insert(ProcessingStatistic).values(
                id=uuid5(batch.id, f"stat:load:{entity_type}"),
                tenant_id=batch.tenant_id,
                batch_id=batch.id,
                step_name="load",
                entity_type=entity_type,
                received_count=count,
                valid_count=count,
                rejected_count=0,
                duplicate_count=0,
                bytes_received=0,
                duration_ms=duration_ms,
                records_per_second=Decimal(count * 1_000) / Decimal(duration_ms),
            )
            await session.execute(
                statistic.on_conflict_do_update(
                    index_elements=["tenant_id", "batch_id", "step_name", "entity_type"],
                    set_={
                        "received_count": count,
                        "valid_count": count,
                        "duration_ms": duration_ms,
                        "records_per_second": Decimal(count * 1_000) / Decimal(duration_ms),
                    },
                )
            )
        batch.progress_percent = 90
        _finish_step(step, ProcessingState.LOADING)
        await session.commit()
    finally:
        await session.close()
    finalize_batch.send(str(batch_id), str(tenant_id), correlation_id)


@dramatiq.actor(
    queue_name="integration-process", max_retries=5, min_backoff=2_000, max_backoff=120_000
)
def load_batch(batch_id: str, tenant_id: str, correlation_id: str = "") -> None:
    try:
        _run(_load_batch(UUID(batch_id), UUID(tenant_id), correlation_id))
    except Exception as exc:
        _actor_failure(batch_id, tenant_id, "load", exc)
        raise


async def _finalize_batch(batch_id: UUID, tenant_id: UUID, correlation_id: str) -> None:
    session = await _tenant_session(tenant_id)
    try:
        batch = await session.scalar(
            select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update()
        )
        if (
            batch is None
            or is_terminal_state(batch.state)
            or batch.state != ProcessingState.LOADING
        ):
            return
        blocking = int(
            await session.scalar(
                select(func.count(ProcessingError.id)).where(
                    ProcessingError.batch_id == batch.id,
                    ProcessingError.severity == "blocking",
                )
            )
            or 0
        )
        warnings = int(
            await session.scalar(
                select(func.count(ProcessingError.id)).where(
                    ProcessingError.batch_id == batch.id,
                    ProcessingError.severity.in_(("warning", "error")),
                )
            )
            or 0
        )
        if blocking:
            target = ProcessingState.QUARANTINED
        elif warnings or batch.rejected_records:
            target = ProcessingState.COMPLETED_WITH_WARNINGS
        else:
            target = ProcessingState.COMPLETED
        await transition_batch(
            session,
            batch,
            target,
            actor_type="worker",
            actor_id="finalize",
            reason=f"loaded={batch.valid_records}; rejected={batch.rejected_records}",
        )
        batch.progress_percent = 100
        batch.completed_at = datetime.now(UTC)
        event_type = f"integration.batch.{target.value}"
        session.add(
            OutboxEvent(
                tenant_id=batch.tenant_id,
                aggregate_type="import_batch",
                aggregate_id=batch.id,
                event_type=event_type,
                idempotency_key=f"{batch.id}:{event_type}",
                payload={
                    "batch_id": str(batch.id),
                    "data_source_id": str(batch.data_source_id),
                    "state": target.value,
                    "received_records": batch.received_records,
                    "valid_records": batch.valid_records,
                    "rejected_records": batch.rejected_records,
                    "correlation_id": correlation_id,
                },
            )
        )
        await session.commit()
    finally:
        await session.close()
    publish_outbox.send(str(tenant_id))


@dramatiq.actor(
    queue_name="integration-process", max_retries=5, min_backoff=2_000, max_backoff=120_000
)
def finalize_batch(batch_id: str, tenant_id: str, correlation_id: str = "") -> None:
    try:
        _run(_finalize_batch(UUID(batch_id), UUID(tenant_id), correlation_id))
    except Exception as exc:
        _actor_failure(batch_id, tenant_id, "finalize", exc)
        raise


async def _publish_outbox(tenant_id: UUID) -> None:
    session = await _tenant_session(tenant_id)
    try:
        events = list(
            (
                await session.scalars(
                    select(OutboxEvent)
                    .where(OutboxEvent.published_at.is_(None))
                    .order_by(OutboxEvent.created_at)
                    .limit(100)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        now = datetime.now(UTC)
        for event in events:
            logger.info(
                "integration_outbox_event",
                event_type=event.event_type,
                aggregate_id=str(event.aggregate_id),
                tenant_id=str(event.tenant_id),
            )
            event.publish_attempts += 1
            event.published_at = now
        await session.commit()
    finally:
        await session.close()


@dramatiq.actor(queue_name="integration-notifications", max_retries=8, min_backoff=5_000)
def publish_outbox(tenant_id: str) -> None:
    _run(_publish_outbox(UUID(tenant_id)))


async def _cleanup_expired_landing(tenant_id: UUID) -> int:
    session = await _tenant_session(tenant_id)
    storage = get_object_storage()
    try:
        expired = list(
            (
                await session.scalars(
                    select(ImportedFile).where(
                        ImportedFile.retention_until < date.today(),
                        ImportedFile.immutable.is_(False),
                    )
                )
            ).all()
        )
        for imported_file in expired:
            storage.delete_object(imported_file.object_key)
            await session.delete(imported_file)
        await session.commit()
        return len(expired)
    finally:
        await session.close()


@dramatiq.actor(queue_name="integration-maintenance", max_retries=3)
def cleanup_expired_landing(tenant_id: str) -> int:
    return int(_run(_cleanup_expired_landing(UUID(tenant_id))))
