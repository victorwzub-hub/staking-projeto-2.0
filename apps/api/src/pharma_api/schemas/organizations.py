from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    slug: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class TenantUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    expected_version: int = Field(ge=1)


class EconomicGroupCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=180)


class EconomicGroupUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    status: str | None = Field(default=None, pattern=r"^(active|inactive|archived)$")
    expected_version: int = Field(ge=1)


class ArchiveRequest(BaseModel):
    expected_version: int = Field(ge=1)


class EconomicGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    name: str
    status: str
    version: int


class CompanyCreateRequest(BaseModel):
    legal_name: str = Field(min_length=2, max_length=220)
    trade_name: str = Field(min_length=2, max_length=180)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    economic_group_id: UUID | None = None


class CompanyUpdateRequest(BaseModel):
    legal_name: str | None = Field(default=None, min_length=2, max_length=220)
    trade_name: str | None = Field(default=None, min_length=2, max_length=180)
    status: str | None = Field(default=None, pattern=r"^(active|inactive|archived)$")
    expected_version: int = Field(ge=1)


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    economic_group_id: UUID | None
    legal_name: str
    trade_name: str
    slug: str
    status: str
    version: int


class BranchCreateRequest(BaseModel):
    company_id: UUID
    name: str = Field(min_length=2, max_length=180)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")


class BranchUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    status: str | None = Field(default=None, pattern=r"^(active|inactive|archived)$")
    expected_version: int = Field(ge=1)


class BranchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    company_id: UUID
    name: str
    slug: str
    status: str
    version: int


class MembershipResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    user_id: UUID
    email: EmailStr
    display_name: str
    status: str
    title: str | None
    roles: list[str]
    version: int


class MembershipUpdateRequest(BaseModel):
    status: str = Field(pattern=r"^(active|suspended|revoked)$")
    expected_version: int = Field(ge=1)


class TeamCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=500)


class TeamUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    expected_version: int = Field(ge=1)


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    version: int


class TeamMemberRequest(BaseModel):
    membership_id: UUID


class TeamMembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    team_id: UUID
    membership_id: UUID


class InvitationCreateRequest(BaseModel):
    email: EmailStr
    role_id: UUID
    company_id: UUID | None = None
    branch_id: UUID | None = None


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=20, max_length=256)


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    normalized_email: EmailStr
    role_id: UUID
    company_id: UUID | None
    branch_id: UUID | None
    status: str
    expires_at: datetime
    created_at: datetime
