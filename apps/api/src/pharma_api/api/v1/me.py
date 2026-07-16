from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from pharma_api.api.dependencies import CSRFProtectedAuth, CurrentAuth, DBSession
from pharma_api.application.auth.context import list_user_contexts, switch_context
from pharma_api.application.auth.profile import list_security_events, update_profile
from pharma_api.schemas.auth import (
    BranchContextResponse,
    CompanyContextResponse,
    ContextSwitchRequest,
    MembershipContextResponse,
    MeResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    SecurityEventResponse,
    SessionResponse,
    UserResponse,
)
from pharma_api.schemas.common import MessageResponse

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeResponse)
async def get_me(session: DBSession, auth: CurrentAuth) -> MeResponse:
    contexts = await list_user_contexts(session, auth)
    return MeResponse(
        user=UserResponse(
            id=auth.user.id,
            email=auth.user.email,
            status=auth.user.status,
            email_verified_at=auth.user.email_verified_at,
            is_platform_admin=auth.user.is_platform_admin,
            display_name=auth.profile.display_name,
        ),
        active_session=SessionResponse.model_validate(auth.session).model_copy(
            update={"current": True}
        ),
        contexts=[
            MembershipContextResponse(
                membership_id=context.membership_id,
                tenant_id=context.tenant_id,
                tenant_name=context.tenant_name,
                status=context.status,
                companies=[
                    CompanyContextResponse(
                        id=company.id,
                        name=company.name,
                        branches=[
                            BranchContextResponse(id=branch.id, name=branch.name)
                            for branch in company.branches
                        ],
                    )
                    for company in context.companies
                ],
            )
            for context in contexts
        ],
        permissions=sorted(auth.permission_keys),
    )


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(auth: CurrentAuth) -> ProfileResponse:
    return ProfileResponse.model_validate(auth.profile)


@router.patch("/profile", response_model=ProfileResponse)
async def patch_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    session: DBSession,
    auth: CSRFProtectedAuth,
) -> ProfileResponse:
    profile = await update_profile(
        session,
        auth=auth,
        display_name=payload.display_name,
        locale=payload.locale,
        timezone=payload.timezone,
        expected_version=payload.expected_version,
        correlation_id=request.state.correlation_id,
    )
    return ProfileResponse.model_validate(profile)


@router.get("/security-events", response_model=list[SecurityEventResponse])
async def get_security_events(
    session: DBSession,
    auth: CurrentAuth,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SecurityEventResponse]:
    events = await list_security_events(
        session,
        user_id=auth.user.id,
        limit=limit,
        offset=offset,
    )
    return [SecurityEventResponse.model_validate(event) for event in events]


@router.post("/context", response_model=MessageResponse)
async def change_context(
    payload: ContextSwitchRequest,
    request: Request,
    session: DBSession,
    auth: CSRFProtectedAuth,
) -> MessageResponse:
    await switch_context(
        session,
        auth=auth,
        tenant_id=payload.tenant_id,
        company_id=payload.company_id,
        branch_id=payload.branch_id,
        correlation_id=request.state.correlation_id,
    )
    return MessageResponse(message="Active context updated.")
