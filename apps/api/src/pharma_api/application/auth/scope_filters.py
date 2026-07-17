from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import and_, exists, false, or_, select
from sqlalchemy.sql.elements import ColumnElement

from pharma_api.application.auth.types import AuthContext
from pharma_api.infrastructure.db.models.operations import AuditEvent, Invitation
from pharma_api.infrastructure.db.models.organizations import (
    Branch,
    Company,
    EconomicGroup,
    Membership,
)
from pharma_api.infrastructure.db.models.rbac import Role, RoleAssignment


def _tenant_id(auth: AuthContext) -> UUID | None:
    if auth.tenant_id is None:
        return None
    return auth.tenant_id


def _expression(value: object) -> ColumnElement[bool]:
    return cast(ColumnElement[bool], value)


def company_visibility_filter(auth: AuthContext, permission_key: str) -> ColumnElement[bool]:
    tenant_id = _tenant_id(auth)
    if tenant_id is None:
        return _expression(false())
    access = auth.scope_access(permission_key, tenant_id)
    if access.tenant_wide:
        return _expression(Company.tenant_id == tenant_id)
    visible_ids = access.visible_company_ids
    if not visible_ids:
        return _expression(false())
    return _expression(and_(Company.tenant_id == tenant_id, Company.id.in_(visible_ids)))


def branch_visibility_filter(auth: AuthContext, permission_key: str) -> ColumnElement[bool]:
    tenant_id = _tenant_id(auth)
    if tenant_id is None:
        return _expression(false())
    access = auth.scope_access(permission_key, tenant_id)
    if access.tenant_wide:
        return _expression(Branch.tenant_id == tenant_id)
    scoped: list[ColumnElement[bool]] = []
    if access.company_ids:
        scoped.append(Branch.company_id.in_(access.company_ids))
    if access.branch_ids:
        scoped.append(Branch.id.in_(access.branch_ids))
    if not scoped:
        return _expression(false())
    return _expression(and_(Branch.tenant_id == tenant_id, or_(*scoped)))


def economic_group_visibility_filter(auth: AuthContext, permission_key: str) -> ColumnElement[bool]:
    tenant_id = _tenant_id(auth)
    if tenant_id is None:
        return _expression(false())
    access = auth.scope_access(permission_key, tenant_id)
    if access.tenant_wide:
        return _expression(EconomicGroup.tenant_id == tenant_id)
    visible_company_ids = access.visible_company_ids
    if not visible_company_ids:
        return _expression(false())
    linked_company = exists(
        select(1).where(
            Company.tenant_id == tenant_id,
            Company.economic_group_id == EconomicGroup.id,
            Company.id.in_(visible_company_ids),
        )
    )
    return _expression(and_(EconomicGroup.tenant_id == tenant_id, linked_company))


def audit_event_visibility_filter(auth: AuthContext, permission_key: str) -> ColumnElement[bool]:
    tenant_id = _tenant_id(auth)
    if tenant_id is None:
        return _expression(false())
    access = auth.scope_access(permission_key, tenant_id)
    if access.tenant_wide:
        return _expression(AuditEvent.tenant_id == tenant_id)
    scoped: list[ColumnElement[bool]] = []
    if access.company_ids:
        scoped.append(AuditEvent.company_id.in_(access.company_ids))
    if access.branch_ids:
        scoped.append(AuditEvent.branch_id.in_(access.branch_ids))
    if not scoped:
        return _expression(false())
    return _expression(and_(AuditEvent.tenant_id == tenant_id, or_(*scoped)))


def invitation_visibility_filter(auth: AuthContext, permission_key: str) -> ColumnElement[bool]:
    tenant_id = _tenant_id(auth)
    if tenant_id is None:
        return _expression(false())
    access = auth.scope_access(permission_key, tenant_id)
    if access.tenant_wide:
        return _expression(Invitation.tenant_id == tenant_id)
    scoped: list[ColumnElement[bool]] = []
    if access.company_ids:
        scoped.append(Invitation.company_id.in_(access.company_ids))
    if access.branch_ids:
        scoped.append(Invitation.branch_id.in_(access.branch_ids))
    if not scoped:
        return _expression(false())
    return _expression(and_(Invitation.tenant_id == tenant_id, or_(*scoped)))


def role_assignment_visibility_filter(
    auth: AuthContext, permission_key: str
) -> ColumnElement[bool]:
    tenant_id = _tenant_id(auth)
    if tenant_id is None:
        return _expression(false())
    access = auth.scope_access(permission_key, tenant_id)
    if access.tenant_wide:
        return _expression(RoleAssignment.tenant_id == tenant_id)
    scoped: list[ColumnElement[bool]] = []
    if access.company_ids:
        scoped.append(RoleAssignment.company_id.in_(access.company_ids))
    if access.branch_ids:
        scoped.append(RoleAssignment.branch_id.in_(access.branch_ids))
    if not scoped:
        return _expression(false())
    return _expression(and_(RoleAssignment.tenant_id == tenant_id, or_(*scoped)))


def membership_visibility_filter(auth: AuthContext, permission_key: str) -> ColumnElement[bool]:
    tenant_id = _tenant_id(auth)
    if tenant_id is None:
        return _expression(false())
    access = auth.scope_access(permission_key, tenant_id)
    if access.tenant_wide:
        return _expression(Membership.tenant_id == tenant_id)
    scoped: list[ColumnElement[bool]] = []
    if access.company_ids:
        scoped.append(RoleAssignment.company_id.in_(access.company_ids))
    if access.branch_ids:
        scoped.append(RoleAssignment.branch_id.in_(access.branch_ids))
    if not scoped:
        return _expression(false())
    assignment_exists = exists(
        select(1).where(
            RoleAssignment.tenant_id == tenant_id,
            RoleAssignment.membership_id == Membership.id,
            or_(*scoped),
        )
    )
    return _expression(and_(Membership.tenant_id == tenant_id, assignment_exists))


def role_visibility_filter(auth: AuthContext, permission_key: str) -> ColumnElement[bool]:
    tenant_id = _tenant_id(auth)
    if tenant_id is None:
        if auth.user.is_platform_admin:
            return _expression(Role.scope == "platform")
        return _expression(false())
    access = auth.scope_access(permission_key, tenant_id)
    if access.tenant_wide:
        return _expression(
            or_(
                Role.tenant_id == tenant_id,
                and_(Role.tenant_id.is_(None), Role.scope != "platform"),
            )
        )
    if access.company_ids:
        return _expression(
            and_(
                or_(Role.tenant_id == tenant_id, Role.tenant_id.is_(None)),
                Role.scope.in_(("company", "branch")),
            )
        )
    if access.branch_ids:
        return _expression(
            and_(
                or_(Role.tenant_id == tenant_id, Role.tenant_id.is_(None)),
                Role.scope == "branch",
            )
        )
    return false()
