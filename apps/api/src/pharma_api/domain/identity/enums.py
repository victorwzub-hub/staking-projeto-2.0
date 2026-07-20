from enum import StrEnum


class UserStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ANONYMIZED = "anonymized"


class MembershipStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class TokenPurpose(StrEnum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"  # noqa: S105
    INVITATION = "invitation"


class SecurityEventType(StrEnum):
    REGISTERED = "registered"
    EMAIL_VERIFIED = "email_verified"
    LOGIN_SUCCEEDED = "login_succeeded"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"  # noqa: S105
    PASSWORD_RESET_COMPLETED = "password_reset_completed"  # noqa: S105
    PASSWORD_CHANGED = "password_changed"  # noqa: S105
    SESSION_CREATED = "session_created"
    SESSION_REVOKED = "session_revoked"
    SESSION_REFRESHED = "session_refreshed"
    ACCESS_DENIED = "access_denied"
