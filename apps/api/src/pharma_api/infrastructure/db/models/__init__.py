# Import the Phase 2B/2C modules so SQLAlchemy and Alembic always receive complete metadata.
from pharma_api.infrastructure.db.models.analytics import *  # noqa: F403
from pharma_api.infrastructure.db.models.canonical import *  # noqa: F403
from pharma_api.infrastructure.db.models.diagnostics import *  # noqa: F403
from pharma_api.infrastructure.db.models.identity import (
    AuthenticationAttempt,
    EmailVerificationToken,
    PasswordResetToken,
    SecurityEvent,
    Session,
    User,
    UserProfile,
)
from pharma_api.infrastructure.db.models.integration import *  # noqa: F403
from pharma_api.infrastructure.db.models.operations import (
    AuditEvent,
    ConsentRecord,
    Invitation,
    TermsVersion,
)
from pharma_api.infrastructure.db.models.organizations import (
    Branch,
    Company,
    EconomicGroup,
    Membership,
    OnboardingProgress,
    Team,
    TeamMembership,
    Tenant,
)
from pharma_api.infrastructure.db.models.rbac import (
    Permission,
    Role,
    RoleAssignment,
    RolePermission,
)

__all__ = [
    "AuditEvent",
    "AuthenticationAttempt",
    "Branch",
    "Company",
    "ConsentRecord",
    "EconomicGroup",
    "EmailVerificationToken",
    "Invitation",
    "Membership",
    "OnboardingProgress",
    "PasswordResetToken",
    "Permission",
    "Role",
    "RoleAssignment",
    "RolePermission",
    "SecurityEvent",
    "Session",
    "Team",
    "TeamMembership",
    "Tenant",
    "TermsVersion",
    "User",
    "UserProfile",
]
