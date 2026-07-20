from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class PlatformUserResponse(BaseModel):
    id: UUID
    email: EmailStr
    display_name: str
    status: str
    email_verified_at: datetime | None
    is_platform_admin: bool
    version: int
    created_at: datetime


class PlatformUserStatusRequest(BaseModel):
    status: str = Field(pattern=r"^(active|suspended)$")
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=8, max_length=500)
