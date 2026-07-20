from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pharma_api.infrastructure.db.models.identity import Session, User, UserProfile
from pharma_api.infrastructure.db.models.organizations import Membership

_VALID_SCOPES = frozenset({"platform", "tenant", "company", "branch"})


@dataclass(frozen=True, slots=True)
class AuthorizationTarget:
    """A resource location that must be covered by an authorization grant."""

    tenant_id: UUID
    company_id: UUID | None = None
    branch_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.branch_id is not None and self.company_id is None:
            raise ValueError("A branch authorization target requires a company")

    @property
    def scope(self) -> str:
        if self.branch_id is not None:
            return "branch"
        if self.company_id is not None:
            return "company"
        return "tenant"


@dataclass(frozen=True, slots=True)
class PermissionGrant:
    """One permission granted through a role assignment at a verified scope."""

    key: str
    scope: str
    tenant_id: UUID | None = None
    company_id: UUID | None = None
    branch_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.scope not in _VALID_SCOPES:
            raise ValueError(f"Unsupported authorization scope: {self.scope}")
        if self.scope == "platform":
            identifiers = (self.tenant_id, self.company_id, self.branch_id)
            if any(value is not None for value in identifiers):
                raise ValueError(
                    "Platform grants cannot carry tenant, company or branch identifiers"
                )
            return
        if self.tenant_id is None:
            raise ValueError("Non-platform grants require a tenant")
        if self.scope == "tenant":
            if self.company_id is not None or self.branch_id is not None:
                raise ValueError("Tenant grants cannot carry company or branch identifiers")
            return
        if self.company_id is None:
            raise ValueError("Company and branch grants require a company")
        if self.scope == "company":
            if self.branch_id is not None:
                raise ValueError("Company grants cannot carry a branch identifier")
            return
        if self.branch_id is None:
            raise ValueError("Branch grants require a branch")

    def covers_resource(self, target: AuthorizationTarget) -> bool:
        """Return whether this grant covers a resource in the target hierarchy."""

        if self.scope == "platform":
            return True
        if self.tenant_id != target.tenant_id:
            return False
        if target.scope == "tenant":
            # Contextual tenant identity may be read by any grant in that tenant. Tenant-wide
            # resources must use AuthContext.has_tenant_wide_permission instead.
            return True
        if self.scope == "tenant":
            return True
        if self.company_id != target.company_id:
            return False
        if target.scope == "company":
            # A branch-scoped grant may cover its own parent company for the same key.
            return True
        if self.scope == "company":
            return True
        return self.branch_id == target.branch_id

    def covers_delegation(self, target: AuthorizationTarget) -> bool:
        """Return whether this grant may be delegated at the target scope.

        Delegation is stricter than resource access: a child scope can read an allowed
        parent resource, but it can never create an assignment at a broader scope.
        """

        if self.scope == "platform":
            return True
        if self.tenant_id != target.tenant_id:
            return False
        if target.scope == "tenant":
            return self.scope == "tenant"
        if self.scope == "tenant":
            return True
        if self.company_id != target.company_id:
            return False
        if target.scope == "company":
            return self.scope == "company"
        if self.scope == "company":
            return True
        return self.branch_id == target.branch_id


@dataclass(frozen=True, slots=True)
class PermissionScopeAccess:
    """Materialized visibility for one permission inside one tenant."""

    tenant_wide: bool
    company_ids: frozenset[UUID]
    branch_ids: frozenset[UUID]
    branch_company_ids: frozenset[UUID]

    @property
    def visible_company_ids(self) -> frozenset[UUID]:
        return self.company_ids | self.branch_company_ids

    @property
    def has_access(self) -> bool:
        return self.tenant_wide or bool(self.company_ids) or bool(self.branch_ids)


@dataclass(slots=True)
class AuthContext:
    """Authenticated principal plus server-resolved permission grants."""

    user: User
    profile: UserProfile
    session: Session
    membership: Membership | None
    permission_grants: frozenset[PermissionGrant]

    @property
    def tenant_id(self) -> UUID | None:
        return self.session.active_tenant_id

    @property
    def company_id(self) -> UUID | None:
        return self.session.active_company_id

    @property
    def branch_id(self) -> UUID | None:
        return self.session.active_branch_id

    @property
    def permission_keys(self) -> frozenset[str]:
        """Compatibility view for clients that only display effective permission names."""

        return frozenset(grant.key for grant in self.permission_grants)

    def grants_for(self, permission_key: str) -> tuple[PermissionGrant, ...]:
        return tuple(grant for grant in self.permission_grants if grant.key == permission_key)

    def has_permission(self, permission_key: str) -> bool:
        return any(grant.key == permission_key for grant in self.permission_grants)

    def scope_access(self, permission_key: str, tenant_id: UUID) -> PermissionScopeAccess:
        tenant_wide = False
        company_ids: set[UUID] = set()
        branch_ids: set[UUID] = set()
        branch_company_ids: set[UUID] = set()
        for grant in self.grants_for(permission_key):
            if grant.scope == "platform":
                tenant_wide = True
                continue
            if grant.tenant_id != tenant_id:
                continue
            if grant.scope == "tenant":
                tenant_wide = True
            elif grant.scope == "company":
                assert grant.company_id is not None
                company_ids.add(grant.company_id)
            else:
                assert grant.company_id is not None
                assert grant.branch_id is not None
                branch_company_ids.add(grant.company_id)
                branch_ids.add(grant.branch_id)
        return PermissionScopeAccess(
            tenant_wide=tenant_wide,
            company_ids=frozenset(company_ids),
            branch_ids=frozenset(branch_ids),
            branch_company_ids=frozenset(branch_company_ids),
        )

    def has_tenant_wide_permission(self, permission_key: str, tenant_id: UUID) -> bool:
        return self.scope_access(permission_key, tenant_id).tenant_wide

    def can_access(self, permission_key: str, target: AuthorizationTarget) -> bool:
        return any(
            grant.key == permission_key and grant.covers_resource(target)
            for grant in self.permission_grants
        )

    def can_delegate(self, permission_key: str, target: AuthorizationTarget) -> bool:
        return any(
            grant.key == permission_key and grant.covers_delegation(target)
            for grant in self.permission_grants
        )
