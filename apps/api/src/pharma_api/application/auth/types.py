from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pharma_api.infrastructure.db.models.identity import Session, User, UserProfile
from pharma_api.infrastructure.db.models.organizations import Membership


@dataclass(slots=True)
class AuthContext:
    """Authenticated principal plus the server-authorized active scope."""

    user: User
    profile: UserProfile
    session: Session
    membership: Membership | None
    permission_keys: frozenset[str]

    @property
    def tenant_id(self) -> UUID | None:
        return self.session.active_tenant_id

    @property
    def company_id(self) -> UUID | None:
        return self.session.active_company_id

    @property
    def branch_id(self) -> UUID | None:
        return self.session.active_branch_id
