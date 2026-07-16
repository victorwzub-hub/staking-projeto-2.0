from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from pharma_api.api.dependencies import (
    CSRFProtectedAuth,
    DBSession,
    require_permission,
)
from pharma_api.application.auth.types import AuthContext
from pharma_api.application.organizations.service import get_active_tenant, update_tenant
from pharma_api.schemas.organizations import TenantResponse, TenantUpdateRequest

router = APIRouter(prefix="/tenants", tags=["tenants"])
TenantReader = Annotated[AuthContext, Depends(require_permission("tenant.read"))]
TenantWriter = Annotated[AuthContext, Depends(require_permission("tenant.update"))]


@router.get("/current", response_model=TenantResponse)
async def current_tenant(session: DBSession, auth: TenantReader) -> TenantResponse:
    return TenantResponse.model_validate(await get_active_tenant(session, auth))


@router.patch("/current", response_model=TenantResponse)
async def patch_current_tenant(
    payload: TenantUpdateRequest,
    request: Request,
    session: DBSession,
    auth: TenantWriter,
    _csrf: CSRFProtectedAuth,
) -> TenantResponse:
    tenant = await update_tenant(
        session,
        auth=auth,
        name=payload.name,
        expected_version=payload.expected_version,
        correlation_id=request.state.correlation_id,
    )
    return TenantResponse.model_validate(tenant)
