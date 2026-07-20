from pharma_api.domain.identity.enums import (
    MembershipStatus,
    SecurityEventType,
    TokenPurpose,
    UserStatus,
)
from pharma_api.domain.rbac.enums import ScopeType
from pharma_api.domain.tenancy.enums import OnboardingStatus, OrganizationStatus, TenantStatus


def test_domain_enum_contracts_are_stable() -> None:
    assert UserStatus.ACTIVE.value == "active"
    assert MembershipStatus.SUSPENDED.value == "suspended"
    assert TokenPurpose.INVITATION.value == "invitation"
    assert SecurityEventType.SESSION_REVOKED.value == "session_revoked"
    assert ScopeType.BRANCH.value == "branch"
    assert TenantStatus.ACTIVE.value == "active"
    assert OrganizationStatus.INACTIVE.value == "inactive"
    assert OnboardingStatus.COMPLETED.value == "completed"
