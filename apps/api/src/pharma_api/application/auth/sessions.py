from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.audit.service import AuditRecord, append_audit_event
from pharma_api.application.auth.types import AuthContext
from pharma_api.core.config import Settings, get_settings
from pharma_api.core.errors import AppError
from pharma_api.core.security import generate_token, hash_session_token
from pharma_api.infrastructure.db.models.identity import Session


@dataclass(frozen=True, slots=True)
class RotatedSession:
    raw_session_token: str
    raw_csrf_token: str
    session: Session


async def list_sessions(session: AsyncSession, auth: AuthContext) -> list[Session]:
    return list(
        (
            await session.scalars(
                select(Session)
                .where(Session.user_id == auth.user.id)
                .order_by(Session.created_at.desc())
            )
        ).all()
    )


async def revoke_session(
    session: AsyncSession,
    *,
    auth: AuthContext,
    session_id: UUID,
    correlation_id: str | None,
) -> None:
    target = await session.scalar(
        select(Session)
        .where(Session.id == session_id, Session.user_id == auth.user.id)
        .with_for_update()
    )
    if target is None:
        await append_audit_event(
            session,
            AuditRecord(
                action="session.revoke_denied",
                category="identity",
                outcome="denied",
                actor_user_id=auth.user.id,
                effective_user_id=auth.user.id,
                tenant_id=auth.tenant_id,
                company_id=auth.company_id,
                branch_id=auth.branch_id,
                resource_type="session",
                resource_id=str(session_id),
                correlation_id=correlation_id,
            ),
        )
        await session.commit()
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    if target.revoked_at is None:
        target.revoked_at = datetime.now(UTC)
        target.revocation_reason = "user_revoked"
    await append_audit_event(
        session,
        AuditRecord(
            action="session.revoked",
            category="identity",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=auth.tenant_id,
            resource_type="session",
            resource_id=str(target.id),
            correlation_id=correlation_id,
        ),
    )


async def revoke_all_sessions(
    session: AsyncSession,
    *,
    auth: AuthContext,
    include_current: bool,
    correlation_id: str | None,
) -> int:
    now = datetime.now(UTC)
    filters = [Session.user_id == auth.user.id, Session.revoked_at.is_(None)]
    if not include_current:
        filters.append(Session.id != auth.session.id)
    result = await session.execute(
        update(Session).where(*filters).values(revoked_at=now, revocation_reason="user_revoked_all")
    )
    count = int(getattr(result, "rowcount", 0) or 0)
    await append_audit_event(
        session,
        AuditRecord(
            action="session.revoked_all",
            category="identity",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=auth.tenant_id,
            resource_type="user",
            resource_id=str(auth.user.id),
            correlation_id=correlation_id,
            metadata={"count": count, "include_current": include_current},
        ),
    )
    return count


async def rotate_current_session(
    session: AsyncSession,
    *,
    auth: AuthContext,
    correlation_id: str | None,
    settings: Settings | None = None,
) -> RotatedSession:
    config = settings or get_settings()
    raw_session_token = generate_token(48)
    raw_csrf_token = generate_token(32)
    now = datetime.now(UTC)
    auth.session.token_hash = hash_session_token(raw_session_token, config)
    auth.session.csrf_token_hash = hash_session_token(raw_csrf_token, config)
    auth.session.last_seen_at = now
    auth.session.expires_at = now + timedelta(seconds=config.session_ttl_seconds)
    await append_audit_event(
        session,
        AuditRecord(
            action="session.refreshed",
            category="identity",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=auth.tenant_id,
            resource_type="session",
            resource_id=str(auth.session.id),
            correlation_id=correlation_id,
        ),
    )
    return RotatedSession(raw_session_token, raw_csrf_token, auth.session)
