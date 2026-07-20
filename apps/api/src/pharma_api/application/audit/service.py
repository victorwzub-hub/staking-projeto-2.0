from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.infrastructure.db.models.operations import AuditEvent

_SENSITIVE_KEYS = {
    "password",
    "current_password",
    "new_password",
    "token",
    "session_token",
    "csrf_token",
    "cookie",
    "authorization",
    "password_hash",
}


def sanitize_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]"
            if str(key).casefold() in _SENSITIVE_KEYS
            else sanitize_metadata(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple | set):
        return [sanitize_metadata(item) for item in value]
    if isinstance(value, str):
        return value[:1_000]
    if value is None or isinstance(value, int | float | bool):
        return value
    return repr(value)[:1_000]


@dataclass(frozen=True, slots=True)
class AuditRecord:
    action: str
    category: str
    outcome: str
    actor_user_id: UUID | None = None
    effective_user_id: UUID | None = None
    tenant_id: UUID | None = None
    company_id: UUID | None = None
    branch_id: UUID | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    correlation_id: str | None = None
    ip_hash: str | None = None
    user_agent: str | None = None
    changed_fields: list[str] = field(default_factory=list)
    justification: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


async def append_audit_event(session: AsyncSession, record: AuditRecord) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=record.actor_user_id,
        effective_user_id=record.effective_user_id,
        tenant_id=record.tenant_id,
        company_id=record.company_id,
        branch_id=record.branch_id,
        action=record.action,
        category=record.category,
        resource_type=record.resource_type,
        resource_id=record.resource_id,
        outcome=record.outcome,
        correlation_id=record.correlation_id,
        ip_hash=record.ip_hash,
        user_agent=record.user_agent,
        changed_fields=record.changed_fields,
        justification=record.justification,
        metadata_json=sanitize_metadata(record.metadata),
        created_at=datetime.now(UTC),
    )
    session.add(event)
    return event
