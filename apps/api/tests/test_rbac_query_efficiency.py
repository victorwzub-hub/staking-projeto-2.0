from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.auth.types import AuthContext, PermissionScopeAccess
from pharma_api.application.rbac.service import list_roles
from pharma_api.infrastructure.db.models.rbac import Role


@pytest.mark.asyncio
async def test_list_roles_fetches_all_permissions_in_one_round_trip() -> None:
    tenant_id = uuid4()
    role_a = Role(
        id=uuid4(),
        tenant_id=tenant_id,
        name="Administrators",
        slug="administrators",
        scope="tenant",
        is_system=False,
        is_editable=True,
    )
    role_b = Role(
        id=uuid4(),
        tenant_id=tenant_id,
        name="Empty role",
        slug="empty-role",
        scope="tenant",
        is_system=False,
        is_editable=True,
    )
    query_result = MagicMock()
    query_result.all.return_value = [
        (role_a, "company.read"),
        (role_a, "role.read"),
        (role_b, None),
    ]
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = query_result
    auth = MagicMock(spec=AuthContext)
    auth.tenant_id = tenant_id
    auth.scope_access.return_value = PermissionScopeAccess(
        tenant_wide=True,
        company_ids=frozenset(),
        branch_ids=frozenset(),
        branch_company_ids=frozenset(),
    )

    roles = await list_roles(session, auth)

    assert session.execute.await_count == 1
    assert roles == [
        (role_a, ["company.read", "role.read"]),
        (role_b, []),
    ]
