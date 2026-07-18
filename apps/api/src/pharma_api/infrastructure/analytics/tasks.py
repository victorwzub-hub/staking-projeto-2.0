from __future__ import annotations

# ruff: noqa: E501 -- long lines occur only inside parameterized SQL statements.
import asyncio
from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import UUID

import dramatiq
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.analytics.processing import execute_refresh
from pharma_api.core.logging import get_logger
from pharma_api.infrastructure.db.context import RLSContext, apply_rls_context
from pharma_api.infrastructure.db.models.analytics import AnalyticsDataVersion, AnalyticsRefreshJob
from pharma_api.infrastructure.db.models.integration import ImportBatch
from pharma_api.infrastructure.db.session import get_session_factory
from pharma_api.infrastructure.messaging.broker import configure_broker

configure_broker()
logger = get_logger(__name__)


def _run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


async def _tenant_session(tenant_id: UUID) -> AsyncSession:
    session = get_session_factory()()
    await apply_rls_context(session, RLSContext(tenant_id=tenant_id))
    return session


async def _batch_window(session: AsyncSession, batch: ImportBatch) -> tuple[datetime, datetime]:
    row = (
        await session.execute(
            text(
                """SELECT min(event_at),max(event_at) FROM (
                  SELECT occurred_at AS event_at FROM canonical_sales WHERE tenant_id=:tenant_id AND batch_id=:batch_id
                  UNION ALL SELECT ordered_at FROM canonical_purchase_orders WHERE tenant_id=:tenant_id AND batch_id=:batch_id
                  UNION ALL SELECT snapshot_at FROM canonical_stock_snapshots WHERE tenant_id=:tenant_id AND batch_id=:batch_id
                  UNION ALL SELECT occurred_at FROM canonical_inventory_movements WHERE tenant_id=:tenant_id AND batch_id=:batch_id
                  UNION ALL SELECT valid_from FROM canonical_product_prices WHERE tenant_id=:tenant_id AND batch_id=:batch_id
                  UNION ALL SELECT valid_from FROM canonical_promotions WHERE tenant_id=:tenant_id AND batch_id=:batch_id
                ) events"""
            ),
            {"tenant_id": batch.tenant_id, "batch_id": batch.id},
        )
    ).one()
    start_at = row[0]
    end_at = row[1]
    if start_at is None:
        start_date = batch.period_start or batch.created_at.date()
        start_at = datetime.combine(start_date, time.min, tzinfo=UTC)
    if end_at is None:
        end_date = batch.period_end or batch.created_at.date()
        end_at = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=UTC)
    else:
        end_at = datetime.combine(end_at.date() + timedelta(days=1), time.min, tzinfo=UTC)
    batch_end = datetime.combine(batch.created_at.date() + timedelta(days=1), time.min, tzinfo=UTC)
    end_at = max(end_at, batch_end)
    # Re-open a bounded lookback so late corrections repair rolling calculations.
    return start_at - timedelta(days=7), end_at


async def _enqueue_batch(batch_id: UUID, tenant_id: UUID, correlation_id: str) -> UUID | None:
    session = await _tenant_session(tenant_id)
    try:
        batch = await session.scalar(
            select(ImportBatch).where(
                ImportBatch.id == batch_id, ImportBatch.tenant_id == tenant_id
            )
        )
        if batch is None or batch.state not in {"completed", "completed_with_warnings"}:
            return None
        idempotency_key = f"batch:{batch.id}:analytics:{batch.version}"
        existing = await session.scalar(
            select(AnalyticsRefreshJob).where(
                AnalyticsRefreshJob.tenant_id == tenant_id,
                AnalyticsRefreshJob.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return existing.id
        window_start, window_end = await _batch_window(session, batch)
        version_row = await session.scalar(
            select(AnalyticsDataVersion).where(AnalyticsDataVersion.tenant_id == tenant_id)
        )
        job = AnalyticsRefreshJob(
            tenant_id=tenant_id,
            trigger_type="import_batch",
            source_batch_id=batch.id,
            idempotency_key=idempotency_key,
            state="queued",
            window_start=window_start,
            window_end=window_end,
            watermark_before=version_row.watermark if version_row else None,
            checkpoint={"step": "queued", "correlation_id": correlation_id},
            metrics={},
        )
        session.add(job)
        await session.flush()
        job_id = job.id
        await session.commit()
        return job_id
    finally:
        await session.close()


@dramatiq.actor(
    queue_name="analytics-refresh", max_retries=5, min_backoff=2_000, max_backoff=120_000
)
def enqueue_batch_analytics(batch_id: str, tenant_id: str, correlation_id: str = "") -> None:
    job_id = _run(_enqueue_batch(UUID(batch_id), UUID(tenant_id), correlation_id))
    if job_id is not None:
        refresh_analytics.send(str(job_id), tenant_id)


async def _mark_failed(job_id: UUID, tenant_id: UUID, exc: Exception) -> None:
    session = await _tenant_session(tenant_id)
    try:
        job = await session.scalar(
            select(AnalyticsRefreshJob).where(AnalyticsRefreshJob.id == job_id).with_for_update()
        )
        if job is not None and job.state != "cancelled":
            job.state = "failed"
            job.error_code = type(exc).__name__[:120]
            job.error_message = str(exc)[:2_000]
            job.completed_at = datetime.now(UTC)
            job.version += 1
            await session.commit()
    finally:
        await session.close()


async def _refresh(job_id: UUID, tenant_id: UUID) -> dict[str, int | float]:
    session = await _tenant_session(tenant_id)
    lock_key = f"analytics:{tenant_id}"
    locked = False
    try:
        locked = bool(
            await session.scalar(
                text("SELECT pg_try_advisory_lock(hashtextextended(:lock_key,0))"),
                {"lock_key": lock_key},
            )
        )
        if not locked:
            raise RuntimeError("another analytical refresh holds the tenant lease")
        job = await session.scalar(
            select(AnalyticsRefreshJob)
            .where(AnalyticsRefreshJob.id == job_id, AnalyticsRefreshJob.tenant_id == tenant_id)
            .with_for_update()
        )
        if job is None:
            return {}
        if job.state == "completed":
            return {
                key: value for key, value in job.metrics.items() if isinstance(value, int | float)
            }
        if job.cancel_requested_at is not None:
            job.state = "cancelled"
            job.completed_at = datetime.now(UTC)
            job.version += 1
            await session.commit()
            return {}
        job.state = "running"
        job.started_at = datetime.now(UTC)
        job.completed_at = None
        job.error_code = None
        job.error_message = None
        job.attempt_count += 1
        job.version += 1
        await session.commit()
        # set_config(..., true) is transaction-local. Re-apply tenant context
        # before the warehouse transaction that follows the visible state change.
        await apply_rls_context(session, RLSContext(tenant_id=tenant_id))
        metrics = await execute_refresh(session, job)
        cancelled_after_processing = (
            await session.scalar(
                select(AnalyticsRefreshJob.cancel_requested_at).where(
                    AnalyticsRefreshJob.id == job.id
                )
            )
        ) is not None
        if cancelled_after_processing:
            await session.rollback()
            job.state = "cancelled"
        else:
            job.state = "completed"
            job.completed_at = datetime.now(UTC)
            job.version += 1
        await session.commit()
        logger.info(
            "analytics_refresh_completed",
            tenant_id=str(tenant_id),
            job_id=str(job_id),
            **metrics,
        )
        return metrics
    except Exception as exc:
        await session.rollback()
        await _mark_failed(job_id, tenant_id, exc)
        logger.exception(
            "analytics_refresh_failed",
            tenant_id=str(tenant_id),
            job_id=str(job_id),
            error_type=type(exc).__name__,
        )
        raise
    finally:
        if locked:
            await session.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:lock_key,0))"),
                {"lock_key": lock_key},
            )
        await session.close()


@dramatiq.actor(
    queue_name="analytics-refresh", max_retries=5, min_backoff=2_000, max_backoff=120_000
)
def refresh_analytics(job_id: str, tenant_id: str) -> dict[str, int | float]:
    return dict(_run(_refresh(UUID(job_id), UUID(tenant_id))))
