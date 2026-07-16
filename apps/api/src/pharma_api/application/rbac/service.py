from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.audit.service import AuditRecord, append_audit_event
from pharma_api.application.auth.types import AuthContext
from pharma_api.core.errors import AppError
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
    if auth.tenant_id is None and not auth.user.is_platform_admin:
        return []
    roles = (
        await session.scalars(
            select(Role)
            .where((Role.tenant_id == auth.tenant_id) | (Role.tenant_id.is_(None)))
            .order_by(Role.is_system.desc(), Role.name)
        )
    ).all()
    return [(role, sorted(await role_permission_keys(session, role.id))) for role in roles]


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
    if auth.tenant_id is None:
        raise AppError(
            code="tenant_context_required", message="Tenant context required", status_code=400
        )
    requested = frozenset(permission_keys)
    if not requested or not requested.issubset(auth.permission_keys):
        raise AppError(
            code="permission_not_delegable",
            message="One or more permissions cannot be delegated by the current actor",
            status_code=403,
        )
    permissions = (
        await session.scalars(select(Permission).where(Permission.key.in_(requested)))
    ).all()
    if len(permissions) != len(requested):
        raise AppError(code="unknown_permission", message="Unknown permission", status_code=400)

    role = Role(
        id=uuid4(),
        tenant_id=auth.tenant_id,
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
            tenant_id=auth.tenant_id,
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
    role = await session.scalar(select(Role).where(Role.id == role_id).with_for_update())
    if role is None or role.tenant_id != auth.tenant_id:
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
        if not requested or not requested.issubset(auth.permission_keys):
            raise AppError(
                code="permission_not_delegable",
                message="One or more permissions cannot be delegated by the current actor",
                status_code=403,
            )
        permissions = (
            await session.scalars(select(Permission).where(Permission.key.in_(requested)))
        ).all()
        if len(permissions) != len(requested):
            raise AppError(code="unknown_permission", message="Unknown permission", status_code=400)
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
            tenant_id=auth.tenant_id,
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
    role = await session.scalar(select(Role).where(Role.id == role_id).with_for_update())
    if role is None or role.tenant_id != auth.tenant_id:
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
            tenant_id=auth.tenant_id,
            resource_type="role",
            resource_id=str(role.id),
            correlation_id=correlation_id,
        ),
    )


async def _validate_assignment_scope(
    session: AsyncSession,
    *,
    auth: AuthContext,
    role: Role,
    company_id: UUID | None,
    branch_id: UUID | None,
) -> None:
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
        return
    if company_id is None:
        raise AppError(
            code="company_scope_required", message="Company scope is required", status_code=400
        )
    company = await session.scalar(
        select(Company).where(Company.id == company_id, Company.tenant_id == auth.tenant_id)
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
        return
    if branch_id is None:
        raise AppError(
            code="branch_scope_required", message="Branch scope is required", status_code=400
        )
    branch = await session.scalar(
        select(Branch).where(
            Branch.id == branch_id,
            Branch.tenant_id == auth.tenant_id,
            Branch.company_id == company_id,
        )
    )
    if branch is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)


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
    if auth.tenant_id is None:
        raise AppError(
            code="tenant_context_required", message="Tenant context required", status_code=400
        )
    membership = await session.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.tenant_id == auth.tenant_id,
        )
    )
    role = await session.scalar(
        select(Role).where(
            Role.id == role_id,
            (Role.tenant_id == auth.tenant_id) | (Role.tenant_id.is_(None)),
        )
    )
    if membership is None or role is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    delegated = await role_permission_keys(session, role.id)
    if not delegated.issubset(auth.permission_keys):
        raise AppError(
            code="role_not_delegable",
            message="The selected role exceeds the actor's delegable permissions",
            status_code=403,
        )
    await _validate_assignment_scope(
        session,
        auth=auth,
        role=role,
        company_id=company_id,
        branch_id=branch_id,
    )

    assignment = RoleAssignment(
        id=uuid4(),
        tenant_id=auth.tenant_id,
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
            tenant_id=auth.tenant_id,
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
    assignment = await session.scalar(
        select(RoleAssignment)
        .where(
            RoleAssignment.id == assignment_id,
            RoleAssignment.tenant_id == auth.tenant_id,
        )
        .with_for_update()
    )
    if assignment is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    role = await session.get(Role, assignment.role_id)
    if role is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    if role.slug == "tenant_owner":
        owner_count = await session.scalar(
            select(func.count())
            .select_from(RoleAssignment)
            .join(Membership, Membership.id == RoleAssignment.membership_id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                RoleAssignment.tenant_id == auth.tenant_id,
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
            tenant_id=auth.tenant_id,
            company_id=assignment.company_id,
            branch_id=assignment.branch_id,
            resource_type="membership",
            resource_id=str(assignment.membership_id),
            correlation_id=correlation_id,
            metadata={"role_id": str(role.id), "assignment_id": str(assignment.id)},
        ),
    )
