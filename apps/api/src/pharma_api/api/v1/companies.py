from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from pharma_api.api.dependencies import (
    CSRFProtectedAuth,
    DBSession,
    require_permission,
)
from pharma_api.application.auth.types import AuthContext
from pharma_api.application.organizations.service import (
    archive_company,
    create_company,
    update_company,
)
from pharma_api.core.errors import AppError
from pharma_api.infrastructure.db.models.organizations import Company
from pharma_api.schemas.common import MessageResponse
from pharma_api.schemas.organizations import (
    ArchiveRequest,
    CompanyCreateRequest,
    CompanyResponse,
    CompanyUpdateRequest,
)

router = APIRouter(prefix="/companies", tags=["companies"])
Reader = Annotated[AuthContext, Depends(require_permission("company.read"))]
Creator = Annotated[AuthContext, Depends(require_permission("company.create"))]
Writer = Annotated[AuthContext, Depends(require_permission("company.update"))]
Deleter = Annotated[AuthContext, Depends(require_permission("company.delete"))]


@router.get("", response_model=list[CompanyResponse])
async def list_companies(session: DBSession, auth: Reader) -> list[CompanyResponse]:
    companies = (
        await session.scalars(
            select(Company).where(Company.tenant_id == auth.tenant_id).order_by(Company.trade_name)
        )
    ).all()
    return [CompanyResponse.model_validate(company) for company in companies]


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(company_id: UUID, session: DBSession, auth: Reader) -> CompanyResponse:
    company = await session.scalar(
        select(Company).where(Company.id == company_id, Company.tenant_id == auth.tenant_id)
    )
    if company is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    return CompanyResponse.model_validate(company)


@router.post("", response_model=CompanyResponse, status_code=201)
async def post_company(
    payload: CompanyCreateRequest,
    request: Request,
    session: DBSession,
    auth: Creator,
    _csrf: CSRFProtectedAuth,
) -> CompanyResponse:
    company = await create_company(
        session,
        auth=auth,
        legal_name=payload.legal_name,
        trade_name=payload.trade_name,
        slug=payload.slug,
        economic_group_id=payload.economic_group_id,
        correlation_id=request.state.correlation_id,
    )
    return CompanyResponse.model_validate(company)


@router.patch("/{company_id}", response_model=CompanyResponse)
async def patch_company(
    company_id: UUID,
    payload: CompanyUpdateRequest,
    request: Request,
    session: DBSession,
    auth: Writer,
    _csrf: CSRFProtectedAuth,
) -> CompanyResponse:
    company = await update_company(
        session,
        auth=auth,
        company_id=company_id,
        legal_name=payload.legal_name,
        trade_name=payload.trade_name,
        status=payload.status,
        expected_version=payload.expected_version,
        correlation_id=request.state.correlation_id,
    )
    return CompanyResponse.model_validate(company)


@router.delete("/{company_id}", response_model=MessageResponse)
async def delete_company(
    company_id: UUID,
    payload: ArchiveRequest,
    request: Request,
    session: DBSession,
    auth: Deleter,
    _csrf: CSRFProtectedAuth,
) -> MessageResponse:
    await archive_company(
        session,
        auth=auth,
        company_id=company_id,
        expected_version=payload.expected_version,
        correlation_id=request.state.correlation_id,
    )
    return MessageResponse(message="Company archived.")
