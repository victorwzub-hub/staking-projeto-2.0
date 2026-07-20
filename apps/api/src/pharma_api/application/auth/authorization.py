from __future__ import annotations

from uuid import UUID

from pharma_api.application.auth.types import AuthContext, AuthorizationTarget
from pharma_api.core.errors import AppError


def require_tenant_context(auth: AuthContext) -> UUID:
    if auth.tenant_id is None:
        raise AppError(
            code="tenant_context_required", message="Tenant context required", status_code=400
        )
    return auth.tenant_id


def require_tenant_wide_permission(auth: AuthContext, permission_key: str) -> UUID:
    tenant_id = require_tenant_context(auth)
    if not auth.has_tenant_wide_permission(permission_key, tenant_id):
        raise AppError(
            code="forbidden",
            message="You do not have permission to perform this action",
            status_code=403,
        )
    return tenant_id


def require_resource_permission(
    auth: AuthContext,
    permission_key: str,
    target: AuthorizationTarget,
    *,
    conceal: bool = True,
) -> None:
    if auth.can_access(permission_key, target):
        return
    if conceal:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    raise AppError(
        code="forbidden",
        message="You do not have permission to perform this action",
        status_code=403,
    )


def require_delegation_permission(
    auth: AuthContext,
    permission_key: str,
    target: AuthorizationTarget,
) -> None:
    if not auth.can_delegate(permission_key, target):
        raise AppError(
            code="permission_not_delegable",
            message="One or more permissions cannot be delegated by the current actor",
            status_code=403,
        )
