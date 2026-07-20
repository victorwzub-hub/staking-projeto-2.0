from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PermissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    key: str
    scope: str
    description: str
    catalog_version: int


class RoleResponse(BaseModel):
    id: UUID
    tenant_id: UUID | None
    name: str
    slug: str
    scope: str
    is_system: bool
    is_editable: bool
    version: int
    permissions: list[str]


class RoleCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    scope: str = Field(pattern=r"^(tenant|company|branch)$")
    description: str | None = Field(default=None, max_length=400)
    permission_keys: list[str] = Field(min_length=1, max_length=100)


class RoleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=400)
    permission_keys: list[str] | None = Field(default=None, max_length=100)
    expected_version: int = Field(ge=1)


class RoleAssignmentRequest(BaseModel):
    membership_id: UUID
    role_id: UUID
    company_id: UUID | None = None
    branch_id: UUID | None = None


class RoleAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    membership_id: UUID
    role_id: UUID
    company_id: UUID | None
    branch_id: UUID | None
    assigned_by_user_id: UUID
