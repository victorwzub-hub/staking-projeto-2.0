from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.audit.service import AuditRecord, append_audit_event
from pharma_api.application.auth.authorization import (
    require_delegation_permission,
    require_tenant_context,
    require_tenant_wide_permission,
)
from pharma_api.application.auth.scope_filters import role_visibility_filter
from pharma_api.application.auth.types import (
    AuthContext,
    AuthorizationTarget,
    PermissionGrant,
)
from pharma_api.core.errors import AppError
from pharma_api.infrastructure.db.models.identity import User
from pharma_api.infrastructure.db.models.organizations import Branch, Company, Membership
from pharma_api.infrastructure.db.models.rbac import (
    Permission,
    Role,
    RoleAssignment,
    RolePermission,
)


async def role_permission_keys(session: AsyncSession, role_id: UUID) -> frozenset[str]:
    statement = (
        select(Permission.key)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
    )
    return frozenset((await session.scalars(statement)).all())


async def list_roles(session: AsyncSession, auth: AuthContext) -> list[tuple[Role, list[str]]]:
    roles = (
        await session.scalars(
            select(Role)
            .where(role_visibility_filter(auth, "role.read"))
            .order_by(Role.is_system.desc(), Role.name)
        )
    ).all()
    return [(role, sorted(await role_permission_keys(session, role.id))) for role in roles]


def _validate_tenant_role_permissions(
    auth: AuthContext,
    tenant_id: UUID,
    requested: frozenset[str],
) -> None:
    if not requested or any(
        not auth.has_tenant_wide_permission(permission_key, tenant_id)
        for permission_key in requested
    ):
        raise AppError(
            code="permission_not_delegable",
            message="One or more permissions cannot be delegated by the current actor",
            status_code=403,
        )


async def _load_permissions(session: AsyncSession, requested: frozenset[str]) -> list[Permission]:
    permissions = (
        await session.scalars(select(Permission).where(Permission.key.in_(requested)))
    ).all()
    if len(permissions) != len(requested):
        raise AppError(code="unknown_permission", message="Unknown permission", status_code=400)
    return list(permissions)


async def create_role(
    session: AsyncSession,
    *,
    auth: AuthContext,
    name: str,
    slug: str,
    scope: str,
    description: str | None,
    permission_keys: list[str],
    correlation_id: str | None,
) -> Role:
    tenant_id = require_tenant_wide_permission(auth, "role.create")
    requested = frozenset(permission_keys)
    _validate_tenant_role_permissions(auth, tenant_id, requested)
    permissions = await _load_permissions(session, requested)

    role = Role(
        id=uuid4(),
        tenant_id=tenant_id,
        name=name,
        slug=slug,
        scope=scope,
        is_system=False,
        is_editable=True,
        description=description,
        version=1,
    )
    session.add(role)
    await session.flush()
    session.add_all(
        [RolePermission(role_id=role.id, permission_id=permission.id) for permission in permissions]
    )
    await append_audit_event(
        session,
        AuditRecord(
            action="role.created",
            category="authorization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            resource_type="role",
            resource_id=str(role.id),
            correlation_id=correlation_id,
            metadata={"permission_keys": sorted(requested), "scope": scope},
        ),
    )
    return role


async def update_role(
    session: AsyncSession,
    *,
    auth: AuthContext,
    role_id: UUID,
    name: str | None,
    description: str | None,
    permission_keys: list[str] | None,
    expected_version: int,
    correlation_id: str | None,
) -> Role:
    tenant_id = require_tenant_wide_permission(auth, "role.update")
    role = await session.scalar(select(Role).where(Role.id == role_id).with_for_update())
    if role is None or role.tenant_id != tenant_id:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    if role.is_system or not role.is_editable:
        raise AppError(
            code="system_role_immutable", message="System roles are immutable", status_code=409
        )
    if role.version != expected_version:
        raise AppError(code="version_conflict", message="Resource was modified", status_code=409)

    changed: list[str] = []
    if name is not None and name != role.name:
        role.name = name
        changed.append("name")
    if description is not None and description != role.description:
        role.description = description
        changed.append("description")
    if permission_keys is not None:
        requested = frozenset(permission_keys)
        _validate_tenant_role_permissions(auth, tenant_id, requested)
        permissions = await _load_permissions(session, requested)
        await session.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        session.add_all(
            [
                RolePermission(role_id=role.id, permission_id=permission.id)
                for permission in permissions
            ]
        )
        changed.append("permissions")
    role.version += 1
    await append_audit_event(
        session,
        AuditRecord(
            action="role.updated",
            category="authorization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            resource_type="role",
            resource_id=str(role.id),
            correlation_id=correlation_id,
            changed_fields=changed,
        ),
    )
    return role


async def delete_role(
    session: AsyncSession,
    *,
    auth: AuthContext,
    role_id: UUID,
    correlation_id: str | None,
) -> None:
    tenant_id = require_tenant_wide_permission(auth, "role.delete")
    role = await session.scalar(select(Role).where(Role.id == role_id).with_for_update())
    if role is None or role.tenant_id != tenant_id:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    if role.is_system:
        raise AppError(
            code="system_role_immutable", message="System roles are immutable", status_code=409
        )
    assignment_count = await session.scalar(
        select(func.count()).select_from(RoleAssignment).where(RoleAssignment.role_id == role.id)
    )
    if assignment_count:
        raise AppError(
            code="role_in_use", message="Role is assigned and cannot be deleted", status_code=409
        )
    await session.delete(role)
    await append_audit_event(
        session,
        AuditRecord(
            action="role.deleted",
            category="authorization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            resource_type="role",
            resource_id=str(role.id),
            correlation_id=correlation_id,
        ),
    )


async def resolve_role_target(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    role: Role,
    company_id: UUID | None,
    branch_id: UUID | None,
) -> AuthorizationTarget:
    if role.scope == "platform":
        raise AppError(
            code="platform_role_assignment_forbidden",
            message="Platform roles cannot be assigned through tenant administration",
            status_code=403,
        )
    if role.scope == "tenant":
        if company_id is not None or branch_id is not None:
            raise AppError(
                code="invalid_role_scope",
                message="Tenant roles cannot be constrained to company or branch",
                status_code=400,
            )
        return AuthorizationTarget(tenant_id=tenant_id)
    if company_id is None:
        raise AppError(
            code="company_scope_required", message="Company scope is required", status_code=400
        )
    company = await session.scalar(
        select(Company).where(Company.id == company_id, Company.tenant_id == tenant_id)
    )
    if company is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    if role.scope == "company":
        if branch_id is not None:
            raise AppError(
                code="invalid_role_scope",
                message="Company roles cannot be constrained to a branch",
                status_code=400,
            )
        return AuthorizationTarget(tenant_id=tenant_id, company_id=company_id)
    if branch_id is None:
        raise AppError(
            code="branch_scope_required", message="Branch scope is required", status_code=400
        )
    branch = await session.scalar(
        select(Branch).where(
            Branch.id == branch_id,
            Branch.tenant_id == tenant_id,
            Branch.company_id == company_id,
        )
    )
    if branch is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    return AuthorizationTarget(
        tenant_id=tenant_id,
        company_id=company_id,
        branch_id=branch_id,
    )


async def validate_role_delegation(
    session: AsyncSession,
    *,
    auth: AuthContext,
    role: Role,
    target: AuthorizationTarget,
    authority_permission: str,
) -> frozenset[str]:
    require_delegation_permission(auth, authority_permission, target)
    delegated = await role_permission_keys(session, role.id)
    if any(not auth.can_delegate(permission_key, target) for permission_key in delegated):
        raise AppError(
            code="role_not_delegable",
            message="The selected role exceeds the actor's delegable permissions",
            status_code=403,
        )
    return delegated


async def validate_inviter_authority(
    session: AsyncSession,
    *,
    user_id: UUID,
    tenant_id: UUID,
    role: Role,
    target: AuthorizationTarget,
) -> None:
    user = await session.get(User, user_id)
    if user is None or user.status != "active":
        raise AppError(
            code="invitation_authority_revoked",
            message="The invitation can no longer be accepted",
            status_code=409,
        )
    if user.is_platform_admin:
        return
    membership = await session.scalar(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.tenant_id == tenant_id,
            Membership.status == "active",
        )
    )
    if membership is None:
        raise AppError(
            code="invitation_authority_revoked",
            message="The invitation can no longer be accepted",
            status_code=409,
        )
    rows = (
        await session.execute(
            select(
                Permission.key,
                Role.scope,
                RoleAssignment.tenant_id,
                RoleAssignment.company_id,
                RoleAssignment.branch_id,
            )
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .where(
                RoleAssignment.membership_id == membership.id,
                RoleAssignment.tenant_id == tenant_id,
            )
        )
    ).all()
    grants = frozenset(
        PermissionGrant(
            key=key,
            scope=scope,
            tenant_id=assignment_tenant_id,
            company_id=company_id,
            branch_id=branch_id,
        )
        for key, scope, assignment_tenant_id, company_id, branch_id in rows
    )
    delegated = await role_permission_keys(session, role.id)
    has_invite_authority = any(
        grant.key == "user.invite" and grant.covers_delegation(target) for grant in grants
    )
    can_delegate_role = all(
        any(grant.key == key and grant.covers_delegation(target) for grant in grants)
        for key in delegated
    )
    if not has_invite_authority or not can_delegate_role:
        raise AppError(
            code="invitation_authority_revoked",
            message="The invitation can no longer be accepted",
            status_code=409,
        )


async def assign_role(
    session: AsyncSession,
    *,
    auth: AuthContext,
    membership_id: UUID,
    role_id: UUID,
    company_id: UUID | None,
    branch_id: UUID | None,
    correlation_id: str | None,
) -> RoleAssignment:
    tenant_id = require_tenant_context(auth)
    membership = await session.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.tenant_id == tenant_id,
        )
    )
    role = await session.scalar(
        select(Role).where(
            Role.id == role_id,
            (Role.tenant_id == tenant_id) | (Role.tenant_id.is_(None)),
        )
    )
    if membership is None or role is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    target = await resolve_role_target(
        session,
        tenant_id=tenant_id,
        role=role,
        company_id=company_id,
        branch_id=branch_id,
    )
    await validate_role_delegation(
        session,
        auth=auth,
        role=role,
        target=target,
        authority_permission="role.assign",
    )

    assignment = RoleAssignment(
        id=uuid4(),
        tenant_id=tenant_id,
        membership_id=membership.id,
        role_id=role.id,
        company_id=company_id,
        branch_id=branch_id,
        assigned_by_user_id=auth.user.id,
    )
    session.add(assignment)
    await append_audit_event(
        session,
        AuditRecord(
            action="role.assigned",
            category="authorization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            company_id=company_id,
            branch_id=branch_id,
            resource_type="membership",
            resource_id=str(membership.id),
            correlation_id=correlation_id,
            metadata={"role_id": str(role.id)},
        ),
    )
    return assignment


async def remove_role_assignment(
    session: AsyncSession,
    *,
    auth: AuthContext,
    assignment_id: UUID,
    correlation_id: str | None,
) -> None:
    tenant_id = require_tenant_context(auth)
    assignment = await session.scalar(
        select(RoleAssignment)
        .where(
            RoleAssignment.id == assignment_id,
            RoleAssignment.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if assignment is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    role = await session.get(Role, assignment.role_id)
    if role is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    target = await resolve_role_target(
        session,
        tenant_id=tenant_id,
        role=role,
        company_id=assignment.company_id,
        branch_id=assignment.branch_id,
    )
    await validate_role_delegation(
        session,
        auth=auth,
        role=role,
        target=target,
        authority_permission="role.assign",
    )
    if role.slug == "tenant_owner":
        owner_count = await session.scalar(
            select(func.count())
            .select_from(RoleAssignment)
            .join(Membership, Membership.id == RoleAssignment.membership_id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                RoleAssignment.tenant_id == tenant_id,
                Role.slug == "tenant_owner",
                Membership.status == "active",
            )
        )
        if int(owner_count or 0) <= 1:
            raise AppError(
                code="last_tenant_owner",
                message="The last tenant owner assignment cannot be removed",
                status_code=409,
            )
    await session.delete(assignment)
    await append_audit_event(
        session,
        AuditRecord(
            action="role.removed",
            category="authorization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            company_id=assignment.company_id,
            branch_id=assignment.branch_id,
            resource_type="membership",
            resource_id=str(assignment.membership_id),
            correlation_id=correlation_id,
            metadata={"role_id": str(role.id), "assignment_id": str(assignment.id)},
        ),
    )
