from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class RLSContext:
    user_id: UUID | None = None
    tenant_id: UUID | None = None
    is_platform_admin: bool = False
    invitation_token_hash: str | None = None


async def apply_rls_context(session: AsyncSession, context: RLSContext) -> None:
    """Apply transaction-local PostgreSQL RLS context without leaking through the pool."""
    values = {
        "user_id": str(context.user_id) if context.user_id else "",
        "tenant_id": str(context.tenant_id) if context.tenant_id else "",
        "is_platform_admin": "true" if context.is_platform_admin else "false",
        "invitation_token_hash": context.invitation_token_hash or "",
    }
    await session.execute(
        text(
            "SELECT "
            "set_config('app.current_user_id', :user_id, true), "
            "set_config('app.current_tenant_id', :tenant_id, true), "
            "set_config('app.is_platform_admin', :is_platform_admin, true), "
            "set_config('app.invitation_token_hash', :invitation_token_hash, true)"
        ),
        values,
    )
