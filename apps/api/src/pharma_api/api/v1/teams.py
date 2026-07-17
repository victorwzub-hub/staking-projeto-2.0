from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from pharma_api.api.dependencies import (
    CSRFProtectedAuth,
    DBSession,
    require_tenant_permission,
)
from pharma_api.application.auth.types import AuthContext
from pharma_api.application.organizations.service import (
    add_team_member,
    create_team,
    delete_team,
    remove_team_member,
    update_team,
)
from pharma_api.core.errors import AppError
from pharma_api.infrastructure.db.models.organizations import Team, TeamMembership
from pharma_api.schemas.common import MessageResponse
from pharma_api.schemas.organizations import (
    TeamCreateRequest,
    TeamMemberRequest,
    TeamMembershipResponse,
    TeamResponse,
    TeamUpdateRequest,
)

router = APIRouter(prefix="/teams", tags=["teams"])
Reader = Annotated[AuthContext, Depends(require_tenant_permission("team.read"))]
Creator = Annotated[AuthContext, Depends(require_tenant_permission("team.create"))]
Updater = Annotated[AuthContext, Depends(require_tenant_permission("team.update"))]
Deleter = Annotated[AuthContext, Depends(require_tenant_permission("team.delete"))]


@router.get("", response_model=list[TeamResponse])
async def list_teams(session: DBSession, auth: Reader) -> list[TeamResponse]:
    teams = (
        await session.scalars(
            select(Team).where(Team.tenant_id == auth.tenant_id).order_by(Team.name)
        )
    ).all()
    return [TeamResponse.model_validate(team) for team in teams]


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(team_id: UUID, session: DBSession, auth: Reader) -> TeamResponse:
    team = await session.scalar(
        select(Team).where(Team.id == team_id, Team.tenant_id == auth.tenant_id)
    )
    if team is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    return TeamResponse.model_validate(team)


@router.post("", response_model=TeamResponse, status_code=201)
async def post_team(
    payload: TeamCreateRequest,
    request: Request,
    session: DBSession,
    auth: Creator,
    _csrf: CSRFProtectedAuth,
) -> TeamResponse:
    team = await create_team(
        session,
        auth=auth,
        name=payload.name,
        description=payload.description,
        correlation_id=request.state.correlation_id,
    )
    return TeamResponse.model_validate(team)


@router.patch("/{team_id}", response_model=TeamResponse)
async def patch_team(
    team_id: UUID,
    payload: TeamUpdateRequest,
    request: Request,
    session: DBSession,
    auth: Updater,
    _csrf: CSRFProtectedAuth,
) -> TeamResponse:
    team = await update_team(
        session,
        auth=auth,
        team_id=team_id,
        name=payload.name,
        description=payload.description,
        expected_version=payload.expected_version,
        correlation_id=request.state.correlation_id,
    )
    return TeamResponse.model_validate(team)


@router.delete("/{team_id}", response_model=MessageResponse)
async def remove_team(
    team_id: UUID,
    request: Request,
    session: DBSession,
    auth: Deleter,
    _csrf: CSRFProtectedAuth,
) -> MessageResponse:
    await delete_team(
        session,
        auth=auth,
        team_id=team_id,
        correlation_id=request.state.correlation_id,
    )
    return MessageResponse(message="Team deleted.")


@router.get("/{team_id}/members", response_model=list[TeamMembershipResponse])
async def list_team_members(
    team_id: UUID, session: DBSession, auth: Reader
) -> list[TeamMembershipResponse]:
    links = (
        await session.scalars(
            select(TeamMembership).where(
                TeamMembership.team_id == team_id,
                TeamMembership.tenant_id == auth.tenant_id,
            )
        )
    ).all()
    return [TeamMembershipResponse.model_validate(link) for link in links]


@router.post("/{team_id}/members", response_model=MessageResponse)
async def post_team_member(
    team_id: UUID,
    payload: TeamMemberRequest,
    request: Request,
    session: DBSession,
    auth: Updater,
    _csrf: CSRFProtectedAuth,
) -> MessageResponse:
    await add_team_member(
        session,
        auth=auth,
        team_id=team_id,
        membership_id=payload.membership_id,
        correlation_id=request.state.correlation_id,
    )
    return MessageResponse(message="Team member added.")


@router.delete("/{team_id}/members/{membership_id}", response_model=MessageResponse)
async def delete_team_member(
    team_id: UUID,
    membership_id: UUID,
    request: Request,
    session: DBSession,
    auth: Updater,
    _csrf: CSRFProtectedAuth,
) -> MessageResponse:
    await remove_team_member(
        session,
        auth=auth,
        team_id=team_id,
        membership_id=membership_id,
        correlation_id=request.state.correlation_id,
    )
    return MessageResponse(message="Team member removed.")
