from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.auth.rate_limit import LoginRateLimiter, RateLimitKey
from pharma_api.application.email.service import (
    EmailCommand,
    password_reset_email,
    verification_email,
)
from pharma_api.core.config import Settings, get_settings
from pharma_api.core.errors import AppError
from pharma_api.core.security import (
    generate_token,
    hash_one_time_token,
    hash_password,
    hash_sensitive_identifier,
    hash_session_token,
    normalize_email,
    safe_user_agent,
    verify_password,
)
from pharma_api.infrastructure.db.context import RLSContext, apply_rls_context
from pharma_api.infrastructure.db.models.identity import (
    AuthenticationAttempt,
    EmailVerificationToken,
    PasswordResetToken,
    SecurityEvent,
    Session,
    User,
    UserProfile,
)
from pharma_api.infrastructure.db.models.organizations import Membership, OnboardingProgress


@dataclass(frozen=True, slots=True)
class RequestMetadata:
    correlation_id: str | None
    ip_address: str | None
    user_agent: str | None

    @property
    def safe_user_agent(self) -> str | None:
        return safe_user_agent(self.user_agent)

    def ip_hash(self, settings: Settings | None = None) -> str | None:
        return hash_sensitive_identifier(self.ip_address, settings)


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    accepted: bool
    email_command: EmailCommand | None = None


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: User
    profile: UserProfile
    session: Session
    raw_session_token: str
    raw_csrf_token: str
    onboarding_required: bool


@dataclass(frozen=True, slots=True)
class TokenResult:
    email_command: EmailCommand | None


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    return hash_password("Unusable-Dummy-Password-8675309")


def _hash_account_password(password: str, settings: Settings) -> str:
    """Apply the configured password policy and expose a controlled client error."""
    try:
        return hash_password(password, settings)
    except ValueError as exc:
        raise AppError(
            code="password_policy_violation",
            message="Password does not satisfy the configured security policy",
            status_code=422,
            details={"reason": str(exc)},
        ) from exc


async def _security_event(
    session: AsyncSession,
    *,
    user_id: UUID | None,
    event_type: str,
    outcome: str,
    metadata: RequestMetadata,
    extra: dict[str, str] | None = None,
) -> None:
    session.add(
        SecurityEvent(
            id=uuid4(),
            user_id=user_id,
            event_type=event_type,
            outcome=outcome,
            correlation_id=metadata.correlation_id,
            ip_hash=metadata.ip_hash(),
            user_agent=metadata.safe_user_agent,
            metadata_json=extra or {},
            created_at=datetime.now(UTC),
        )
    )


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str,
    metadata: RequestMetadata,
    settings: Settings | None = None,
) -> RegistrationResult:
    config = settings or get_settings()
    normalized = normalize_email(email)
    existing = await session.scalar(select(User).where(User.normalized_email == normalized))
    if existing is not None:
        await _security_event(
            session,
            user_id=existing.id,
            event_type="registration_duplicate_suppressed",
            outcome="accepted",
            metadata=metadata,
        )
        return RegistrationResult(accepted=True)

    now = datetime.now(UTC)
    user = User(
        id=uuid4(),
        email=email.strip(),
        normalized_email=normalized,
        password_hash=_hash_account_password(password, config),
        status="pending",
        is_platform_admin=False,
        created_at=now,
        updated_at=now,
        version=1,
    )
    profile = UserProfile(
        user_id=user.id,
        display_name=display_name.strip(),
        locale="pt-BR",
        timezone="America/Sao_Paulo",
        created_at=now,
        updated_at=now,
        version=1,
    )
    raw_token = generate_token()
    token = EmailVerificationToken(
        id=uuid4(),
        user_id=user.id,
        token_hash=hash_one_time_token(raw_token, config),
        expires_at=now + timedelta(seconds=config.email_verification_ttl_seconds),
        created_at=now,
    )
    session.add_all([user, profile, token])
    await _security_event(
        session,
        user_id=user.id,
        event_type="registered",
        outcome="success",
        metadata=metadata,
    )
    return RegistrationResult(
        accepted=True,
        email_command=verification_email(user.email, raw_token, str(token.id), config),
    )


async def verify_email_token(
    session: AsyncSession,
    *,
    raw_token: str,
    metadata: RequestMetadata,
    settings: Settings | None = None,
) -> User:
    config = settings or get_settings()
    now = datetime.now(UTC)
    token_hash = hash_one_time_token(raw_token, config)
    token = await session.scalar(
        select(EmailVerificationToken)
        .where(EmailVerificationToken.token_hash == token_hash)
        .with_for_update()
    )
    if token is None or token.used_at is not None or token.expires_at <= now:
        raise AppError(
            code="invalid_or_expired_token",
            message="The verification token is invalid or expired",
            status_code=400,
        )
    user = await session.get(User, token.user_id, with_for_update=True)
    if user is None:
        raise AppError(code="invalid_token", message="Invalid token", status_code=400)

    token.used_at = now
    user.email_verified_at = now
    user.status = "active"
    user.version += 1
    await _security_event(
        session,
        user_id=user.id,
        event_type="email_verified",
        outcome="success",
        metadata=metadata,
    )
    return user


async def resend_verification(
    session: AsyncSession,
    *,
    email: str,
    metadata: RequestMetadata,
    settings: Settings | None = None,
) -> TokenResult:
    config = settings or get_settings()
    normalized = normalize_email(email)
    user = await session.scalar(select(User).where(User.normalized_email == normalized))
    if user is None or user.email_verified_at is not None or user.status == "anonymized":
        return TokenResult(email_command=None)

    now = datetime.now(UTC)
    await session.execute(
        update(EmailVerificationToken)
        .where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw_token = generate_token()
    token = EmailVerificationToken(
        id=uuid4(),
        user_id=user.id,
        token_hash=hash_one_time_token(raw_token, config),
        expires_at=now + timedelta(seconds=config.email_verification_ttl_seconds),
        created_at=now,
    )
    session.add(token)
    await _security_event(
        session,
        user_id=user.id,
        event_type="verification_resent",
        outcome="accepted",
        metadata=metadata,
    )
    return TokenResult(
        email_command=verification_email(user.email, raw_token, str(token.id), config)
    )


async def authenticate_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    metadata: RequestMetadata,
    rate_limiter: LoginRateLimiter,
    settings: Settings | None = None,
) -> LoginResult:
    config = settings or get_settings()
    normalized = normalize_email(email)
    email_hash = hash_sensitive_identifier(normalized, config)
    assert email_hash is not None
    key = RateLimitKey(email_hash=email_hash, ip_hash=metadata.ip_hash(config))
    try:
        await rate_limiter.ensure_allowed(key)
    except AppError as exc:
        if exc.code == "too_many_attempts":
            now = datetime.now(UTC)
            session.add(
                AuthenticationAttempt(
                    id=uuid4(),
                    normalized_email_hash=email_hash,
                    user_id=None,
                    succeeded=False,
                    failure_reason="rate_limited",
                    ip_hash=metadata.ip_hash(config),
                    user_agent=metadata.safe_user_agent,
                    created_at=now,
                )
            )
            await _security_event(
                session,
                user_id=None,
                event_type="login_blocked",
                outcome="denied",
                metadata=metadata,
                extra={"reason": "rate_limited"},
            )
        raise

    user = await session.scalar(select(User).where(User.normalized_email == normalized))
    verification = verify_password(
        password, user.password_hash if user else _dummy_password_hash(), config
    )
    now = datetime.now(UTC)
    succeeded = bool(
        user and verification.valid and user.status == "active" and user.email_verified_at
    )
    session.add(
        AuthenticationAttempt(
            id=uuid4(),
            normalized_email_hash=email_hash,
            user_id=user.id if user else None,
            succeeded=succeeded,
            failure_reason=None if succeeded else "invalid_credentials",
            ip_hash=metadata.ip_hash(config),
            user_agent=metadata.safe_user_agent,
            created_at=now,
        )
    )
    if not succeeded or user is None:
        await rate_limiter.record_failure(key)
        await _security_event(
            session,
            user_id=user.id if user else None,
            event_type="login_failed",
            outcome="denied",
            metadata=metadata,
        )
        raise AppError(
            code="invalid_credentials",
            message="Invalid email or password",
            status_code=401,
        )

    await rate_limiter.clear(key)
    if verification.replacement_hash:
        user.password_hash = verification.replacement_hash
        user.version += 1

    await apply_rls_context(
        session,
        RLSContext(user_id=user.id, is_platform_admin=user.is_platform_admin),
    )
    membership = await session.scalar(
        select(Membership)
        .where(Membership.user_id == user.id, Membership.status == "active")
        .order_by(Membership.created_at)
        .limit(1)
    )
    raw_session_token = generate_token(48)
    raw_csrf_token = generate_token(32)
    auth_session = Session(
        id=uuid4(),
        user_id=user.id,
        token_hash=hash_session_token(raw_session_token, config),
        csrf_token_hash=hash_session_token(raw_csrf_token, config),
        active_tenant_id=membership.tenant_id if membership else None,
        active_company_id=None,
        active_branch_id=None,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(seconds=config.session_ttl_seconds),
        ip_hash=metadata.ip_hash(config),
        user_agent=metadata.safe_user_agent,
    )
    session.add(auth_session)
    profile = await session.get(UserProfile, user.id)
    if profile is None:
        raise AppError(
            code="profile_missing", message="User profile is unavailable", status_code=500
        )
    progress = await session.scalar(
        select(OnboardingProgress).where(OnboardingProgress.user_id == user.id)
    )
    onboarding_required = membership is None and (
        progress is None or progress.status != "completed"
    )
    await _security_event(
        session,
        user_id=user.id,
        event_type="login_succeeded",
        outcome="success",
        metadata=metadata,
        extra={"session_id": str(auth_session.id)},
    )
    return LoginResult(
        user=user,
        profile=profile,
        session=auth_session,
        raw_session_token=raw_session_token,
        raw_csrf_token=raw_csrf_token,
        onboarding_required=onboarding_required,
    )


async def request_password_reset(
    session: AsyncSession,
    *,
    email: str,
    metadata: RequestMetadata,
    settings: Settings | None = None,
) -> TokenResult:
    config = settings or get_settings()
    user = await session.scalar(
        select(User).where(User.normalized_email == normalize_email(email), User.status == "active")
    )
    if user is None:
        return TokenResult(email_command=None)

    now = datetime.now(UTC)
    await session.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    raw_token = generate_token()
    token = PasswordResetToken(
        id=uuid4(),
        user_id=user.id,
        token_hash=hash_one_time_token(raw_token, config),
        expires_at=now + timedelta(seconds=config.password_reset_ttl_seconds),
        created_at=now,
    )
    session.add(token)
    await _security_event(
        session,
        user_id=user.id,
        event_type="password_reset_requested",
        outcome="accepted",
        metadata=metadata,
    )
    return TokenResult(
        email_command=password_reset_email(user.email, raw_token, str(token.id), config)
    )


async def reset_password(
    session: AsyncSession,
    *,
    raw_token: str,
    new_password: str,
    metadata: RequestMetadata,
    settings: Settings | None = None,
) -> User:
    config = settings or get_settings()
    now = datetime.now(UTC)
    token = await session.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == hash_one_time_token(raw_token, config))
        .with_for_update()
    )
    if token is None or token.used_at is not None or token.expires_at <= now:
        raise AppError(
            code="invalid_or_expired_token",
            message="The reset token is invalid or expired",
            status_code=400,
        )
    user = await session.get(User, token.user_id, with_for_update=True)
    if user is None or user.status != "active":
        raise AppError(code="invalid_token", message="Invalid token", status_code=400)

    user.password_hash = _hash_account_password(new_password, config)
    user.version += 1
    token.used_at = now
    await session.execute(
        update(Session)
        .where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .values(revoked_at=now, revocation_reason="password_reset")
    )
    await _security_event(
        session,
        user_id=user.id,
        event_type="password_reset_completed",
        outcome="success",
        metadata=metadata,
    )
    return user


async def change_password(
    session: AsyncSession,
    *,
    user: User,
    current_session_id: UUID,
    current_password: str,
    new_password: str,
    metadata: RequestMetadata,
    settings: Settings | None = None,
) -> None:
    config = settings or get_settings()
    verification = verify_password(current_password, user.password_hash, config)
    if not verification.valid:
        raise AppError(
            code="invalid_current_password",
            message="Current password is invalid",
            status_code=400,
        )
    user.password_hash = _hash_account_password(new_password, config)
    user.version += 1
    now = datetime.now(UTC)
    await session.execute(
        update(Session)
        .where(
            Session.user_id == user.id,
            Session.id != current_session_id,
            Session.revoked_at.is_(None),
        )
        .values(revoked_at=now, revocation_reason="password_changed")
    )
    await _security_event(
        session,
        user_id=user.id,
        event_type="password_changed",
        outcome="success",
        metadata=metadata,
    )
