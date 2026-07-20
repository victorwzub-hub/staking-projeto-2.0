from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class OnboardingProgressResponse(BaseModel):
    status: str
    current_step: str
    tenant_id: UUID | None
    data: dict[str, str]


class CompleteOnboardingRequest(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=180)
    tenant_slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    economic_group_name: str | None = Field(default=None, max_length=180)
    company_legal_name: str = Field(min_length=2, max_length=220)
    company_trade_name: str = Field(min_length=2, max_length=180)
    company_slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    branch_name: str = Field(min_length=2, max_length=180)
    branch_slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    terms_version_id: UUID
    accept_terms: bool


class CompleteOnboardingResponse(BaseModel):
    tenant_id: UUID
    company_id: UUID
    branch_id: UUID
    membership_id: UUID
    status: str = "completed"
