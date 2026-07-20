from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from pharma_api.schemas.auth import ContextSwitchRequest, MembershipContextResponse


def test_branch_context_requires_company_context() -> None:
    with pytest.raises(ValidationError, match="company_id is required"):
        ContextSwitchRequest(tenant_id=uuid4(), branch_id=uuid4())


def test_context_collection_defaults_are_not_shared() -> None:
    first = MembershipContextResponse(
        membership_id=uuid4(), tenant_id=uuid4(), tenant_name="A", status="active"
    )
    second = MembershipContextResponse(
        membership_id=uuid4(), tenant_id=uuid4(), tenant_name="B", status="active"
    )

    first.companies.append(object())  # type: ignore[arg-type]
    assert second.companies == []
