from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from pharma_api.api.dependencies import CSRFProtectedAuth, CurrentAuth, DBSession
from pharma_api.api.v1.auth import _clear_auth_cookies, _set_auth_cookies
from pharma_api.application.auth.sessions import (
    list_sessions,
    revoke_all_sessions,
    revoke_session,
    rotate_current_session,
)
from pharma_api.core.config import Settings, get_settings
from pharma_api.schemas.auth import SessionResponse
from pharma_api.schemas.common import MessageResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionResponse])
async def get_sessions(session: DBSession, auth: CurrentAuth) -> list[SessionResponse]:
    sessions = await list_sessions(session, auth)
    return [
        SessionResponse.model_validate(item).model_copy(
            update={"current": item.id == auth.session.id}
        )
        for item in sessions
    ]


@router.post("/refresh", response_model=SessionResponse)
async def refresh_session(
    request: Request,
    response: Response,
    session: DBSession,
    auth: CSRFProtectedAuth,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionResponse:
    rotated = await rotate_current_session(
        session,
        auth=auth,
        correlation_id=request.state.correlation_id,
        settings=settings,
    )
    _set_auth_cookies(
        response,
        session_token=rotated.raw_session_token,
        csrf_token=rotated.raw_csrf_token,
        settings=settings,
    )
    return SessionResponse.model_validate(rotated.session).model_copy(update={"current": True})


@router.delete("/{session_id}", response_model=MessageResponse)
async def delete_session(
    session_id: UUID,
    request: Request,
    response: Response,
    session: DBSession,
    auth: CSRFProtectedAuth,
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    await revoke_session(
        session,
        auth=auth,
        session_id=session_id,
        correlation_id=request.state.correlation_id,
    )
    if session_id == auth.session.id:
        _clear_auth_cookies(response, settings)
    return MessageResponse(message="Session revoked.")


@router.delete("", response_model=MessageResponse)
async def delete_all_sessions(
    request: Request,
    response: Response,
    session: DBSession,
    auth: CSRFProtectedAuth,
    settings: Annotated[Settings, Depends(get_settings)],
    include_current: bool = False,
) -> MessageResponse:
    count = await revoke_all_sessions(
        session,
        auth=auth,
        include_current=include_current,
        correlation_id=request.state.correlation_id,
    )
    if include_current:
        _clear_auth_cookies(response, settings)
    return MessageResponse(message=f"{count} session(s) revoked.")
