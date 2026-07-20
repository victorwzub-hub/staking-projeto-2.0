from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from pharma_api.api.dependencies import DBSession, require_permission
from pharma_api.application.auth.scope_filters import audit_event_visibility_filter
from pharma_api.application.auth.types import AuthContext
from pharma_api.infrastructure.db.models.operations import AuditEvent
from pharma_api.schemas.audit import AuditEventResponse
from pharma_api.schemas.common import Page

router = APIRouter(prefix="/audit-events", tags=["audit-events"])
Reader = Annotated[AuthContext, Depends(require_permission("audit.read"))]


@router.get("", response_model=Page[AuditEventResponse])
async def list_audit_events(
    session: DBSession,
    auth: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    action: str | None = None,
) -> Page[AuditEventResponse]:
    filters = [audit_event_visibility_filter(auth, "audit.read")]
    if action:
        filters.append(AuditEvent.action == action)
    total = await session.scalar(select(func.count()).select_from(AuditEvent).where(*filters))
    events = (
        await session.scalars(
            select(AuditEvent)
            .where(*filters)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return Page[AuditEventResponse](
        items=[AuditEventResponse.model_validate(event) for event in events],
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )
