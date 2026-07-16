from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from pharma_api.application.audit.service import AuditRecord, append_audit_event
from pharma_api.core.config import get_settings
from pharma_api.core.security import hash_password, normalize_email
from pharma_api.infrastructure.db.context import RLSContext, apply_rls_context
from pharma_api.infrastructure.db.models.identity import User, UserProfile
from pharma_api.infrastructure.db.session import get_session_factory


async def bootstrap() -> None:
    settings = get_settings()
    if not settings.bootstrap_enabled:
        raise SystemExit("Bootstrap is disabled. Set BOOTSTRAP_ENABLED=true explicitly.")
    if not settings.bootstrap_admin_email or settings.bootstrap_admin_password is None:
        raise SystemExit("BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD are required.")

    normalized_email = normalize_email(settings.bootstrap_admin_email)
    password = settings.bootstrap_admin_password.get_secret_value()
    factory = get_session_factory()
    async with factory() as session, session.begin():
        user = await session.scalar(
            select(User).where(User.normalized_email == normalized_email).with_for_update()
        )
        now = datetime.now(UTC)
        created = False
        if user is None:
            try:
                password_hash = hash_password(password, settings)
            except ValueError as exc:
                raise SystemExit(
                    "Bootstrap password does not satisfy the configured security policy."
                ) from exc
            user = User(
                id=uuid4(),
                email=settings.bootstrap_admin_email.strip(),
                normalized_email=normalized_email,
                password_hash=password_hash,
                status="active",
                email_verified_at=now,
                is_platform_admin=True,
                version=1,
            )
            session.add(user)
            await session.flush()
            session.add(
                UserProfile(
                    user_id=user.id,
                    user=user,
                    display_name="Platform Administrator",
                    locale="pt-BR",
                    timezone="America/Sao_Paulo",
                    version=1,
                )
            )
            created = True
        elif not user.is_platform_admin:
            user.is_platform_admin = True
            user.version += 1

        await session.flush()
        await apply_rls_context(
            session,
            RLSContext(user_id=user.id, is_platform_admin=True),
        )
        await append_audit_event(
            session,
            AuditRecord(
                action="platform_admin.bootstrapped",
                category="platform",
                outcome="success",
                actor_user_id=user.id,
                effective_user_id=user.id,
                resource_type="user",
                resource_id=str(user.id),
                metadata={"created": created},
            ),
        )
    print(f"Platform administrator ready: user_id={user.id}")


def main() -> None:
    asyncio.run(bootstrap())


if __name__ == "__main__":
    main()
