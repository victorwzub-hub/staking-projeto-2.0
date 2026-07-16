from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    actor_user_id: UUID | None
    effective_user_id: UUID | None
    tenant_id: UUID | None
    company_id: UUID | None
    branch_id: UUID | None
    action: str
    category: str
    resource_type: str | None
    resource_id: str | None
    outcome: str
    correlation_id: str | None
    changed_fields: list[str]
    justification: str | None
    metadata_json: dict[str, Any]
    created_at: datetime
