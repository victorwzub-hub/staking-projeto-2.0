from enum import StrEnum


class TenantStatus(StrEnum):
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class OrganizationStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class OnboardingStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
