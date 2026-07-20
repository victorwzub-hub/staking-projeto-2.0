from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from pharma_api.api.dependencies import DBSession, require_permission
from pharma_api.application.auth.types import AuthContext
from pharma_api.application.organizations.service import list_memberships
from pharma_api.schemas.organizations import MembershipResponse

router = APIRouter(prefix="/users", tags=["users"])
Reader = Annotated[AuthContext, Depends(require_permission("user.read"))]


@router.get("", response_model=list[MembershipResponse])
async def list_tenant_users(session: DBSession, auth: Reader) -> list[MembershipResponse]:
    return [
        MembershipResponse.model_validate(item) for item in await list_memberships(session, auth)
    ]
