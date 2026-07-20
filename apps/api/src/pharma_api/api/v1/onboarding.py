from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select

from pharma_api.api.dependencies import (
    CSRFProtectedAuth,
    CurrentAuth,
    DBSession,
    get_request_metadata,
)
from pharma_api.application.onboarding.service import complete_onboarding, get_progress
from pharma_api.core.security import hash_sensitive_identifier
from pharma_api.infrastructure.db.models.operations import TermsVersion
from pharma_api.schemas.onboarding import (
    CompleteOnboardingRequest,
    CompleteOnboardingResponse,
    OnboardingProgressResponse,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("", response_model=OnboardingProgressResponse)
async def onboarding_status(session: DBSession, auth: CurrentAuth) -> OnboardingProgressResponse:
    progress = await get_progress(session, auth)
    return OnboardingProgressResponse(
        status=progress.status,
        current_step=progress.current_step,
        tenant_id=progress.tenant_id,
        data={str(key): str(value) for key, value in progress.data_json.items()},
    )


@router.get("/terms", response_model=list[dict[str, str]])
async def active_terms(session: DBSession) -> list[dict[str, str]]:
    terms = (
        await session.scalars(
            select(TermsVersion)
            .where(TermsVersion.is_active.is_(True))
            .order_by(TermsVersion.effective_at)
        )
    ).all()
    return [
        {"id": str(item.id), "document_type": item.document_type, "version": item.version}
        for item in terms
    ]


@router.post("/complete", response_model=CompleteOnboardingResponse)
async def finish_onboarding(
    payload: CompleteOnboardingRequest,
    request: Request,
    session: DBSession,
    auth: CSRFProtectedAuth,
) -> CompleteOnboardingResponse:
    metadata = get_request_metadata(request)
    result = await complete_onboarding(
        session,
        auth=auth,
        tenant_name=payload.tenant_name,
        tenant_slug=payload.tenant_slug,
        economic_group_name=payload.economic_group_name,
        company_legal_name=payload.company_legal_name,
        company_trade_name=payload.company_trade_name,
        company_slug=payload.company_slug,
        branch_name=payload.branch_name,
        branch_slug=payload.branch_slug,
        terms_version_id=payload.terms_version_id,
        accept_terms=payload.accept_terms,
        correlation_id=request.state.correlation_id,
        ip_hash=hash_sensitive_identifier(metadata.ip_address),
    )
    return CompleteOnboardingResponse(
        tenant_id=result.tenant_id,
        company_id=result.company_id,
        branch_id=result.branch_id,
        membership_id=result.membership_id,
    )
