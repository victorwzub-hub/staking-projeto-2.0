from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from pharma_api.api.dependencies import (
    CSRFProtectedAuth,
    DBSession,
    get_login_rate_limiter,
    get_public_auth_rate_limiter,
    get_request_metadata,
)
from pharma_api.application.auth.rate_limit import LoginRateLimiter, PublicAuthRateLimiter
from pharma_api.application.auth.service import (
    authenticate_user,
    change_password,
    register_user,
    request_password_reset,
    resend_verification,
    reset_password,
    verify_email_token,
)
from pharma_api.application.auth.sessions import revoke_all_sessions, revoke_session
from pharma_api.application.email.service import EmailCommand, enqueue_email
from pharma_api.core.config import Settings, get_settings
from pharma_api.core.errors import AppError
from pharma_api.core.logging import get_logger
from pharma_api.core.security import hash_sensitive_identifier
from pharma_api.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SessionResponse,
    UserResponse,
    VerifyEmailRequest,
)
from pharma_api.schemas.common import MessageResponse

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


async def _limit_public_action(
    limiter: PublicAuthRateLimiter,
    *,
    action: str,
    subject: str,
    request: Request,
) -> None:
    metadata = get_request_metadata(request)
    await limiter.consume(
        action=action,
        subject_hash=hash_sensitive_identifier(subject) or "unknown",
        ip_hash=metadata.ip_hash(get_settings()),
    )


def _set_auth_cookies(
    response: Response,
    *,
    session_token: str,
    csrf_token: str,
    settings: Settings,
) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain,
        path="/",
        max_age=settings.session_ttl_seconds,
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain,
        path="/",
        max_age=settings.session_ttl_seconds,
    )


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    for cookie_name in (settings.session_cookie_name, settings.csrf_cookie_name):
        response.delete_cookie(
            key=cookie_name,
            domain=settings.session_cookie_domain,
            path="/",
            secure=settings.session_cookie_secure,
            samesite=settings.session_cookie_samesite,
        )


def _dispatch_email(command: EmailCommand | None) -> None:
    if command is None:
        return
    try:
        enqueue_email(command)
    except Exception as exc:
        logger.error("email_enqueue_failed", error_type=type(exc).__name__)


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: DBSession,
    limiter: Annotated[PublicAuthRateLimiter, Depends(get_public_auth_rate_limiter)],
) -> MessageResponse:
    await _limit_public_action(
        limiter, action="register", subject=str(payload.email), request=request
    )
    result = await register_user(
        session,
        email=str(payload.email),
        password=payload.password,
        display_name=payload.display_name,
        metadata=get_request_metadata(request),
    )
    await session.commit()
    _dispatch_email(result.email_command)
    return MessageResponse(
        message="If registration can be completed, verification instructions will be sent."
    )


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    session: DBSession,
    limiter: Annotated[PublicAuthRateLimiter, Depends(get_public_auth_rate_limiter)],
) -> MessageResponse:
    await _limit_public_action(limiter, action="verify", subject=payload.token, request=request)
    await verify_email_token(
        session,
        raw_token=payload.token,
        metadata=get_request_metadata(request),
    )
    return MessageResponse(message="Email verified successfully.")


@router.post("/resend-verification", response_model=MessageResponse, status_code=202)
async def resend_email_verification(
    payload: ResendVerificationRequest,
    request: Request,
    session: DBSession,
    limiter: Annotated[PublicAuthRateLimiter, Depends(get_public_auth_rate_limiter)],
) -> MessageResponse:
    await _limit_public_action(
        limiter, action="resend", subject=str(payload.email), request=request
    )
    result = await resend_verification(
        session,
        email=str(payload.email),
        metadata=get_request_metadata(request),
    )
    await session.commit()
    _dispatch_email(result.email_command)
    return MessageResponse(message="If the account exists, verification instructions will be sent.")


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: DBSession,
    rate_limiter: Annotated[LoginRateLimiter, Depends(get_login_rate_limiter)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
    try:
        result = await authenticate_user(
            session,
            email=str(payload.email),
            password=payload.password,
            metadata=get_request_metadata(request),
            rate_limiter=rate_limiter,
            settings=settings,
        )
    except AppError:
        # Authentication failures are security records and must survive the HTTP error.
        await session.commit()
        raise
    await session.flush()
    _set_auth_cookies(
        response,
        session_token=result.raw_session_token,
        csrf_token=result.raw_csrf_token,
        settings=settings,
    )
    return LoginResponse(
        user=UserResponse(
            id=result.user.id,
            email=result.user.email,
            status=result.user.status,
            email_verified_at=result.user.email_verified_at,
            is_platform_admin=result.user.is_platform_admin,
            display_name=result.profile.display_name,
        ),
        session=SessionResponse.model_validate(result.session).model_copy(update={"current": True}),
        onboarding_required=result.onboarding_required,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    session: DBSession,
    auth: CSRFProtectedAuth,
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    await revoke_session(
        session,
        auth=auth,
        session_id=auth.session.id,
        correlation_id=request.state.correlation_id,
    )
    _clear_auth_cookies(response, settings)
    return MessageResponse(message="Signed out successfully.")


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all(
    request: Request,
    response: Response,
    session: DBSession,
    auth: CSRFProtectedAuth,
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    count = await revoke_all_sessions(
        session,
        auth=auth,
        include_current=True,
        correlation_id=request.state.correlation_id,
    )
    _clear_auth_cookies(response, settings)
    return MessageResponse(message=f"{count} session(s) revoked.")


@router.post("/forgot-password", response_model=MessageResponse, status_code=202)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    session: DBSession,
    limiter: Annotated[PublicAuthRateLimiter, Depends(get_public_auth_rate_limiter)],
) -> MessageResponse:
    await _limit_public_action(
        limiter, action="forgot", subject=str(payload.email), request=request
    )
    result = await request_password_reset(
        session,
        email=str(payload.email),
        metadata=get_request_metadata(request),
    )
    await session.commit()
    _dispatch_email(result.email_command)
    return MessageResponse(message="If the account exists, reset instructions will be sent.")


@router.post("/reset-password", response_model=MessageResponse)
async def password_reset(
    payload: ResetPasswordRequest,
    request: Request,
    session: DBSession,
    limiter: Annotated[PublicAuthRateLimiter, Depends(get_public_auth_rate_limiter)],
) -> MessageResponse:
    await _limit_public_action(limiter, action="reset", subject=payload.token, request=request)
    await reset_password(
        session,
        raw_token=payload.token,
        new_password=payload.new_password,
        metadata=get_request_metadata(request),
    )
    return MessageResponse(message="Password reset successfully. Sign in again.")


@router.post("/change-password", response_model=MessageResponse)
async def authenticated_password_change(
    payload: ChangePasswordRequest,
    request: Request,
    session: DBSession,
    auth: CSRFProtectedAuth,
) -> MessageResponse:
    await change_password(
        session,
        user=auth.user,
        current_session_id=auth.session.id,
        current_password=payload.current_password,
        new_password=payload.new_password,
        metadata=get_request_metadata(request),
    )
    return MessageResponse(message="Password changed successfully.")
