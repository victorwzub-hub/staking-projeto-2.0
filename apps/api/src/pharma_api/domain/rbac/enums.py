from enum import StrEnum


class ScopeType(StrEnum):
    PLATFORM = "platform"
    TENANT = "tenant"
    COMPANY = "company"
    BRANCH = "branch"
