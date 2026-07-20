from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=2, max_length=160)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=20, max_length=256)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    new_password: str = Field(min_length=10, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=160)
    locale: str | None = Field(default=None, min_length=2, max_length=16)
    timezone: str | None = Field(default=None, min_length=3, max_length=64)
    expected_version: int = Field(ge=1)


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    display_name: str
    locale: str
    timezone: str
    version: int


class SecurityEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    outcome: str
    correlation_id: str | None
    user_agent: str | None
    metadata_json: dict[str, Any]
    created_at: datetime


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    status: str
    email_verified_at: datetime | None
    is_platform_admin: bool
    display_name: str | None = None


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    user_agent: str | None
    active_tenant_id: UUID | None
    active_company_id: UUID | None
    active_branch_id: UUID | None
    current: bool = False


class LoginResponse(BaseModel):
    user: UserResponse
    session: SessionResponse
    onboarding_required: bool


class ContextSwitchRequest(BaseModel):
    tenant_id: UUID
    company_id: UUID | None = None
    branch_id: UUID | None = None

    @model_validator(mode="after")
    def validate_scope_hierarchy(self) -> ContextSwitchRequest:
        if self.branch_id is not None and self.company_id is None:
            raise ValueError("company_id is required when branch_id is provided")
        return self


class MembershipContextResponse(BaseModel):
    membership_id: UUID
    tenant_id: UUID
    tenant_name: str
    status: str
    companies: list[CompanyContextResponse] = Field(default_factory=list)


class CompanyContextResponse(BaseModel):
    id: UUID
    name: str
    branches: list[BranchContextResponse] = Field(default_factory=list)


class BranchContextResponse(BaseModel):
    id: UUID
    name: str


class MeResponse(BaseModel):
    user: UserResponse
    active_session: SessionResponse
    contexts: list[MembershipContextResponse]
    permissions: list[str]
