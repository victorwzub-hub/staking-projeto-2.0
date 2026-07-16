from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.audit.service import AuditRecord, append_audit_event
from pharma_api.application.auth.types import AuthContext
from pharma_api.core.errors import AppError
from pharma_api.infrastructure.db.models.identity import SecurityEvent, UserProfile


async def update_profile(
    session: AsyncSession,
    *,
    auth: AuthContext,
    display_name: str | None,
    locale: str | None,
    timezone: str | None,
    expected_version: int,
    correlation_id: str | None,
) -> UserProfile:
    profile = await session.scalar(
        select(UserProfile).where(UserProfile.user_id == auth.user.id).with_for_update()
    )
    if profile is None:
        raise RuntimeError("authenticated profile is missing")
    if profile.version != expected_version:
        raise AppError(code="version_conflict", message="Resource was modified", status_code=409)
    changed: list[str] = []
    for field_name, value in (
        ("display_name", display_name),
        ("locale", locale),
        ("timezone", timezone),
    ):
        if value is not None and getattr(profile, field_name) != value:
            setattr(profile, field_name, value)
            changed.append(field_name)
    profile.version += 1
    await append_audit_event(
        session,
        AuditRecord(
            action="profile.updated",
            category="identity",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=auth.tenant_id,
            resource_type="user_profile",
            resource_id=str(auth.user.id),
            correlation_id=correlation_id,
            changed_fields=changed,
        ),
    )
    return profile


async def list_security_events(
    session: AsyncSession,
    *,
    user_id: UUID,
    limit: int,
    offset: int,
) -> list[SecurityEvent]:
    return list(
        (
            await session.scalars(
                select(SecurityEvent)
                .where(SecurityEvent.user_id == user_id)
                .order_by(SecurityEvent.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
