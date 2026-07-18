from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, false, or_
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from pharma_api.application.auth.types import AuthContext, AuthorizationTarget
from pharma_api.core.errors import AppError


def analytics_visibility_filter(
    auth: AuthContext,
    permission_key: str,
    tenant_column: InstrumentedAttribute[Any],
    company_column: InstrumentedAttribute[Any],
    branch_column: InstrumentedAttribute[Any],
) -> ColumnElement[bool]:
    if auth.tenant_id is None:
        return cast(ColumnElement[bool], false())
    access = auth.scope_access(permission_key, auth.tenant_id)
    if access.tenant_wide:
        return tenant_column == auth.tenant_id
    predicates: list[ColumnElement[bool]] = []
    if access.company_ids:
        predicates.append(cast(ColumnElement[bool], company_column.in_(access.company_ids)))
    if access.branch_ids:
        predicates.append(cast(ColumnElement[bool], branch_column.in_(access.branch_ids)))
    if not predicates:
        return cast(ColumnElement[bool], false())
    return and_(tenant_column == auth.tenant_id, or_(*predicates))


def require_analytics_scope(
    auth: AuthContext,
    permission_key: str,
    *,
    company_id: UUID | None,
    branch_id: UUID | None,
) -> None:
    if auth.tenant_id is None:
        raise AppError(code="tenant_context_required", message="Select a tenant", status_code=409)
    if not auth.can_access(
        permission_key,
        AuthorizationTarget(
            tenant_id=auth.tenant_id,
            company_id=company_id,
            branch_id=branch_id,
        ),
    ):
        raise AppError(
            code="forbidden_scope",
            message="The selected analytical scope is outside your grant",
            status_code=403,
        )
