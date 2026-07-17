from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from pharma_api.application.auth.types import AuthContext, AuthorizationTarget, PermissionGrant
from pharma_api.infrastructure.db.models.identity import Session, User, UserProfile


def _auth(*grants: PermissionGrant) -> AuthContext:
    user_id = uuid4()
    now = datetime.now(UTC)
    tenant_id = next((grant.tenant_id for grant in grants if grant.tenant_id is not None), uuid4())
    return AuthContext(
        user=User(id=user_id, email="scope@example.com", normalized_email="scope@example.com"),
        profile=UserProfile(
            user_id=user_id,
            display_name="Scoped User",
            locale="pt-BR",
            timezone="UTC",
            version=1,
        ),
        session=Session(
            id=uuid4(),
            user_id=user_id,
            token_hash="scope-session-hash",  # noqa: S106
            csrf_token_hash="scope-csrf-hash",  # noqa: S106
            active_tenant_id=tenant_id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=1),
        ),
        membership=None,
        permission_grants=frozenset(grants),
    )


def test_permission_grant_rejects_malformed_scope_identifiers() -> None:
    tenant_id = uuid4()
    company_id = uuid4()

    with pytest.raises(ValueError, match="require a company"):
        PermissionGrant(key="branch.read", scope="branch", tenant_id=tenant_id)
    with pytest.raises(ValueError, match="cannot carry a branch"):
        PermissionGrant(
            key="company.read",
            scope="company",
            tenant_id=tenant_id,
            company_id=company_id,
            branch_id=uuid4(),
        )
    with pytest.raises(ValueError, match="cannot carry tenant"):
        PermissionGrant(key="platform.admin", scope="platform", tenant_id=tenant_id)


def test_tenant_grant_covers_every_child_resource_in_the_same_tenant() -> None:
    tenant_id = uuid4()
    grant = PermissionGrant(key="branch.read", scope="tenant", tenant_id=tenant_id)
    auth = _auth(grant)

    assert auth.can_access("branch.read", AuthorizationTarget(tenant_id))
    assert auth.can_access(
        "branch.read", AuthorizationTarget(tenant_id, company_id=uuid4(), branch_id=uuid4())
    )
    assert not auth.can_access("branch.read", AuthorizationTarget(uuid4()))


def test_company_grant_covers_only_its_company_and_descendant_branches() -> None:
    tenant_id = uuid4()
    company_id = uuid4()
    grant = PermissionGrant(
        key="branch.read", scope="company", tenant_id=tenant_id, company_id=company_id
    )
    auth = _auth(grant)

    assert auth.can_access("branch.read", AuthorizationTarget(tenant_id, company_id=company_id))
    assert auth.can_access(
        "branch.read",
        AuthorizationTarget(tenant_id, company_id=company_id, branch_id=uuid4()),
    )
    assert not auth.can_access(
        "branch.read", AuthorizationTarget(tenant_id, company_id=uuid4(), branch_id=uuid4())
    )


def test_branch_grant_covers_its_branch_and_parent_but_not_siblings() -> None:
    tenant_id = uuid4()
    company_id = uuid4()
    branch_id = uuid4()
    grant = PermissionGrant(
        key="company.read",
        scope="branch",
        tenant_id=tenant_id,
        company_id=company_id,
        branch_id=branch_id,
    )
    auth = _auth(grant)

    assert auth.can_access("company.read", AuthorizationTarget(tenant_id))
    assert auth.can_access("company.read", AuthorizationTarget(tenant_id, company_id=company_id))
    assert auth.can_access(
        "company.read",
        AuthorizationTarget(tenant_id, company_id=company_id, branch_id=branch_id),
    )
    assert not auth.can_access(
        "company.read",
        AuthorizationTarget(tenant_id, company_id=company_id, branch_id=uuid4()),
    )
    assert not auth.can_access("company.read", AuthorizationTarget(tenant_id, company_id=uuid4()))


def test_delegation_never_expands_a_grants_scope() -> None:
    tenant_id = uuid4()
    company_id = uuid4()
    branch_id = uuid4()
    branch_grant = PermissionGrant(
        key="branch.update",
        scope="branch",
        tenant_id=tenant_id,
        company_id=company_id,
        branch_id=branch_id,
    )
    company_grant = PermissionGrant(
        key="branch.update", scope="company", tenant_id=tenant_id, company_id=company_id
    )

    branch_auth = _auth(branch_grant)
    company_auth = _auth(company_grant)

    assert branch_auth.can_delegate(
        "branch.update",
        AuthorizationTarget(tenant_id, company_id=company_id, branch_id=branch_id),
    )
    assert not branch_auth.can_delegate(
        "branch.update", AuthorizationTarget(tenant_id, company_id=company_id)
    )
    assert not branch_auth.can_delegate("branch.update", AuthorizationTarget(tenant_id))
    assert company_auth.can_delegate(
        "branch.update",
        AuthorizationTarget(tenant_id, company_id=company_id, branch_id=uuid4()),
    )
    assert not company_auth.can_delegate(
        "branch.update",
        AuthorizationTarget(tenant_id, company_id=uuid4(), branch_id=uuid4()),
    )


def test_permission_keys_are_derived_without_losing_scoped_grants() -> None:
    tenant_id = uuid4()
    company_id = uuid4()
    auth = _auth(
        PermissionGrant(key="company.read", scope="tenant", tenant_id=tenant_id),
        PermissionGrant(
            key="company.read", scope="company", tenant_id=tenant_id, company_id=company_id
        ),
        PermissionGrant(key="tenant.read", scope="tenant", tenant_id=tenant_id),
    )

    assert auth.permission_keys == frozenset({"company.read", "tenant.read"})
    assert len(auth.grants_for("company.read")) == 2
    assert auth.has_permission("tenant.read")
    assert not auth.has_permission("company.delete")
