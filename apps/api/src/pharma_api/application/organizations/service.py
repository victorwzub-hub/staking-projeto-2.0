from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.audit.service import AuditRecord, append_audit_event
from pharma_api.application.auth.authorization import (
    require_resource_permission,
    require_tenant_context,
    require_tenant_wide_permission,
)
from pharma_api.application.auth.scope_filters import (
    membership_visibility_filter,
    role_assignment_visibility_filter,
)
from pharma_api.application.auth.types import AuthContext, AuthorizationTarget
from pharma_api.application.email.service import EmailCommand, invitation_email
from pharma_api.application.rbac.service import (
    resolve_role_target,
    validate_inviter_authority,
    validate_role_delegation,
)
from pharma_api.core.config import Settings, get_settings
from pharma_api.core.errors import AppError
from pharma_api.core.security import generate_token, hash_one_time_token, normalize_email
from pharma_api.infrastructure.db.context import RLSContext, apply_rls_context
from pharma_api.infrastructure.db.models.identity import User, UserProfile
from pharma_api.infrastructure.db.models.operations import Invitation
from pharma_api.infrastructure.db.models.organizations import (
    Branch,
    Company,
    EconomicGroup,
    Membership,
    Team,
    TeamMembership,
    Tenant,
)
from pharma_api.infrastructure.db.models.rbac import Role, RoleAssignment


async def get_active_tenant(session: AsyncSession, auth: AuthContext) -> Tenant:
    if auth.tenant_id is None:
        raise AppError(
            code="tenant_context_required", message="Tenant context required", status_code=400
        )
    tenant = await session.get(Tenant, auth.tenant_id)
    if tenant is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    return tenant


async def update_tenant(
    session: AsyncSession,
    *,
    auth: AuthContext,
    name: str | None,
    expected_version: int,
    correlation_id: str | None,
) -> Tenant:
    tenant_id = require_tenant_wide_permission(auth, "tenant.update")
    tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    if tenant is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    if tenant.version != expected_version:
        raise AppError(code="version_conflict", message="Resource was modified", status_code=409)
    changed: list[str] = []
    if name is not None and name != tenant.name:
        tenant.name = name
        changed.append("name")
    tenant.version += 1
    await append_audit_event(
        session,
        AuditRecord(
            action="tenant.updated",
            category="organization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant.id,
            resource_type="tenant",
            resource_id=str(tenant.id),
            changed_fields=changed,
            correlation_id=correlation_id,
        ),
    )
    return tenant


async def create_economic_group(
    session: AsyncSession,
    *,
    auth: AuthContext,
    name: str,
    correlation_id: str | None,
) -> EconomicGroup:
    tenant_id = require_tenant_wide_permission(auth, "company.create")
    group = EconomicGroup(
        id=uuid4(),
        tenant_id=tenant_id,
        name=name,
        status="active",
        version=1,
    )
    session.add(group)
    await append_audit_event(
        session,
        AuditRecord(
            action="economic_group.created",
            category="organization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            resource_type="economic_group",
            resource_id=str(group.id),
            correlation_id=correlation_id,
        ),
    )
    return group


async def create_company(
    session: AsyncSession,
    *,
    auth: AuthContext,
    legal_name: str,
    trade_name: str,
    slug: str,
    economic_group_id: UUID | None,
    correlation_id: str | None,
) -> Company:
    tenant_id = require_tenant_wide_permission(auth, "company.create")
    if economic_group_id is not None:
        group = await session.scalar(
            select(EconomicGroup).where(
                EconomicGroup.id == economic_group_id,
                EconomicGroup.tenant_id == tenant_id,
            )
        )
        if group is None:
            raise AppError(code="not_found", message="Resource not found", status_code=404)
    company = Company(
        id=uuid4(),
        tenant_id=tenant_id,
        economic_group_id=economic_group_id,
        legal_name=legal_name,
        trade_name=trade_name,
        slug=slug,
        status="active",
        version=1,
    )
    session.add(company)
    await append_audit_event(
        session,
        AuditRecord(
            action="company.created",
            category="organization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            resource_type="company",
            resource_id=str(company.id),
            correlation_id=correlation_id,
        ),
    )
    return company


async def update_company(
    session: AsyncSession,
    *,
    auth: AuthContext,
    company_id: UUID,
    legal_name: str | None,
    trade_name: str | None,
    status: str | None,
    expected_version: int,
    correlation_id: str | None,
    permission_key: str = "company.update",
) -> Company:
    tenant_id = require_tenant_context(auth)
    company = await session.scalar(
        select(Company)
        .where(Company.id == company_id, Company.tenant_id == tenant_id)
        .with_for_update()
    )
    if company is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    require_resource_permission(
        auth,
        permission_key,
        AuthorizationTarget(tenant_id=tenant_id, company_id=company.id),
    )
    if company.version != expected_version:
        raise AppError(code="version_conflict", message="Resource was modified", status_code=409)
    changed: list[str] = []
    for field, value in (
        ("legal_name", legal_name),
        ("trade_name", trade_name),
        ("status", status),
    ):
        if value is not None and getattr(company, field) != value:
            setattr(company, field, value)
            changed.append(field)
    company.version += 1
    await append_audit_event(
        session,
        AuditRecord(
            action="company.updated",
            category="organization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            company_id=company.id,
            resource_type="company",
            resource_id=str(company.id),
            correlation_id=correlation_id,
            changed_fields=changed,
        ),
    )
    return company


async def create_branch(
    session: AsyncSession,
    *,
    auth: AuthContext,
    company_id: UUID,
    name: str,
    slug: str,
    correlation_id: str | None,
) -> Branch:
    tenant_id = require_tenant_context(auth)
    company = await session.scalar(
        select(Company).where(Company.id == company_id, Company.tenant_id == tenant_id)
    )
    if company is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    require_resource_permission(
        auth,
        "branch.create",
        AuthorizationTarget(tenant_id=tenant_id, company_id=company.id),
    )
    branch = Branch(
        id=uuid4(),
        tenant_id=tenant_id,
        company_id=company.id,
        name=name,
        slug=slug,
        status="active",
        version=1,
    )
    session.add(branch)
    await append_audit_event(
        session,
        AuditRecord(
            action="branch.created",
            category="organization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            company_id=company.id,
            resource_type="branch",
            resource_id=str(branch.id),
            correlation_id=correlation_id,
        ),
    )
    return branch


async def update_branch(
    session: AsyncSession,
    *,
    auth: AuthContext,
    branch_id: UUID,
    name: str | None,
    status: str | None,
    expected_version: int,
    correlation_id: str | None,
    permission_key: str = "branch.update",
) -> Branch:
    tenant_id = require_tenant_context(auth)
    branch = await session.scalar(
        select(Branch)
        .where(Branch.id == branch_id, Branch.tenant_id == tenant_id)
        .with_for_update()
    )
    if branch is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    require_resource_permission(
        auth,
        permission_key,
        AuthorizationTarget(
            tenant_id=tenant_id,
            company_id=branch.company_id,
            branch_id=branch.id,
        ),
    )
    if branch.version != expected_version:
        raise AppError(code="version_conflict", message="Resource was modified", status_code=409)
    changed: list[str] = []
    if name is not None and name != branch.name:
        branch.name = name
        changed.append("name")
    if status is not None and status != branch.status:
        branch.status = status
        changed.append("status")
    branch.version += 1
    await append_audit_event(
        session,
        AuditRecord(
            action="branch.updated",
            category="organization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            company_id=branch.company_id,
            branch_id=branch.id,
            resource_type="branch",
            resource_id=str(branch.id),
            correlation_id=correlation_id,
            changed_fields=changed,
        ),
    )
    return branch


async def list_memberships(session: AsyncSession, auth: AuthContext) -> list[dict[str, object]]:
    tenant_id = auth.tenant_id
    if tenant_id is None:
        return []
    rows = (
        await session.execute(
            select(Membership, User, UserProfile)
            .join(User, User.id == Membership.user_id)
            .join(UserProfile, UserProfile.user_id == User.id)
            .where(membership_visibility_filter(auth, "user.read"))
            .order_by(UserProfile.display_name)
        )
    ).all()
    assignment_filter = role_assignment_visibility_filter(auth, "user.read")
    result: list[dict[str, object]] = []
    for membership, user, profile in rows:
        role_slugs = (
            await session.scalars(
                select(Role.slug)
                .join(RoleAssignment, RoleAssignment.role_id == Role.id)
                .where(
                    RoleAssignment.membership_id == membership.id,
                    assignment_filter,
                )
            )
        ).all()
        result.append(
            {
                "id": membership.id,
                "tenant_id": membership.tenant_id,
                "user_id": user.id,
                "email": user.email,
                "display_name": profile.display_name,
                "status": membership.status,
                "title": membership.title,
                "roles": sorted(role_slugs),
                "version": membership.version,
            }
        )
    return result


async def update_membership_status(
    session: AsyncSession,
    *,
    auth: AuthContext,
    membership_id: UUID,
    status: str,
    expected_version: int,
    correlation_id: str | None,
) -> Membership:
    tenant_id = require_tenant_wide_permission(auth, "membership.manage")
    membership = await session.scalar(
        select(Membership)
        .where(Membership.id == membership_id, Membership.tenant_id == tenant_id)
        .with_for_update()
    )
    if membership is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    if membership.version != expected_version:
        raise AppError(code="version_conflict", message="Resource was modified", status_code=409)
    if status in {"suspended", "revoked"}:
        owner_role = await session.scalar(
            select(Role).where(Role.slug == "tenant_owner", Role.is_system)
        )
        if owner_role is not None:
            is_owner = await session.scalar(
                select(func.count())
                .select_from(RoleAssignment)
                .where(
                    RoleAssignment.membership_id == membership.id,
                    RoleAssignment.role_id == owner_role.id,
                )
            )
            if is_owner:
                active_owner_count = await session.scalar(
                    select(func.count())
                    .select_from(RoleAssignment)
                    .join(Membership, Membership.id == RoleAssignment.membership_id)
                    .where(
                        RoleAssignment.tenant_id == tenant_id,
                        RoleAssignment.role_id == owner_role.id,
                        Membership.status == "active",
                    )
                )
                if active_owner_count == 1:
                    raise AppError(
                        code="last_tenant_owner",
                        message="The last tenant owner cannot be suspended or revoked",
                        status_code=409,
                    )
    membership.status = status
    membership.version += 1
    if status == "revoked":
        membership.revoked_at = datetime.now(UTC)
    await append_audit_event(
        session,
        AuditRecord(
            action="membership.status_changed",
            category="authorization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            resource_type="membership",
            resource_id=str(membership.id),
            correlation_id=correlation_id,
            changed_fields=["status"],
            metadata={"status": status},
        ),
    )
    return membership


async def create_team(
    session: AsyncSession,
    *,
    auth: AuthContext,
    name: str,
    description: str | None,
    correlation_id: str | None,
) -> Team:
    tenant_id = require_tenant_wide_permission(auth, "team.create")
    team = Team(id=uuid4(), tenant_id=tenant_id, name=name, description=description, version=1)
    session.add(team)
    await append_audit_event(
        session,
        AuditRecord(
            action="team.created",
            category="organization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            resource_type="team",
            resource_id=str(team.id),
            correlation_id=correlation_id,
        ),
    )
    return team


async def add_team_member(
    session: AsyncSession,
    *,
    auth: AuthContext,
    team_id: UUID,
    membership_id: UUID,
    correlation_id: str | None,
) -> TeamMembership:
    tenant_id = require_tenant_wide_permission(auth, "team.update")
    team = await session.scalar(select(Team).where(Team.id == team_id, Team.tenant_id == tenant_id))
    membership = await session.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.tenant_id == tenant_id,
        )
    )
    if team is None or membership is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    existing = await session.scalar(
        select(TeamMembership).where(
            TeamMembership.team_id == team.id,
            TeamMembership.membership_id == membership.id,
        )
    )
    if existing is not None:
        return existing
    link = TeamMembership(
        id=uuid4(),
        tenant_id=tenant_id,
        team_id=team.id,
        membership_id=membership.id,
    )
    session.add(link)
    await append_audit_event(
        session,
        AuditRecord(
            action="team.member_added",
            category="organization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            resource_type="team",
            resource_id=str(team.id),
            correlation_id=correlation_id,
            metadata={"membership_id": str(membership.id)},
        ),
    )
    return link


async def create_invitation(
    session: AsyncSession,
    *,
    auth: AuthContext,
    email: str,
    role_id: UUID,
    company_id: UUID | None,
    branch_id: UUID | None,
    correlation_id: str | None,
    settings: Settings | None = None,
) -> tuple[Invitation, EmailCommand]:
    config = settings or get_settings()
    tenant_id = require_tenant_context(auth)
    role = await session.scalar(
        select(Role).where(
            Role.id == role_id,
            (Role.tenant_id == tenant_id) | (Role.tenant_id.is_(None)),
        )
    )
    if role is None:
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
        authority_permission="user.invite",
    )

    normalized_email = normalize_email(email)
    pending = await session.scalar(
        select(Invitation).where(
            Invitation.tenant_id == tenant_id,
            Invitation.normalized_email == normalized_email,
            Invitation.status == "pending",
            Invitation.expires_at > datetime.now(UTC),
        )
    )
    if pending is not None:
        raise AppError(
            code="invitation_already_pending",
            message="An active invitation already exists for this email",
            status_code=409,
        )

    now = datetime.now(UTC)
    raw_token = generate_token()
    invitation = Invitation(
        id=uuid4(),
        tenant_id=tenant_id,
        normalized_email=normalized_email,
        token_hash=hash_one_time_token(raw_token, config),
        role_id=role.id,
        company_id=company_id,
        branch_id=branch_id,
        status="pending",
        expires_at=now + timedelta(seconds=config.invitation_ttl_seconds),
        created_by_user_id=auth.user.id,
        version=1,
    )
    session.add(invitation)
    await append_audit_event(
        session,
        AuditRecord(
            action="invitation.created",
            category="identity",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            company_id=company_id,
            branch_id=branch_id,
            resource_type="invitation",
            resource_id=str(invitation.id),
            correlation_id=correlation_id,
        ),
    )
    return invitation, invitation_email(email, raw_token, str(invitation.id), config)


async def accept_invitation(
    session: AsyncSession,
    *,
    auth: AuthContext,
    raw_token: str,
    correlation_id: str | None,
    settings: Settings | None = None,
) -> Membership:
    config = settings or get_settings()
    token_hash = hash_one_time_token(raw_token, config)
    await apply_rls_context(
        session,
        RLSContext(
            user_id=auth.user.id,
            is_platform_admin=auth.user.is_platform_admin,
            invitation_token_hash=token_hash,
        ),
    )
    invitation = await session.scalar(
        select(Invitation).where(Invitation.token_hash == token_hash).with_for_update()
    )
    now = datetime.now(UTC)
    if (
        invitation is None
        or invitation.status != "pending"
        or invitation.expires_at <= now
        or invitation.normalized_email != auth.user.normalized_email
    ):
        raise AppError(
            code="invalid_or_expired_invitation",
            message="The invitation is invalid or expired",
            status_code=400,
        )

    await apply_rls_context(
        session,
        RLSContext(
            user_id=auth.user.id,
            tenant_id=invitation.tenant_id,
            is_platform_admin=auth.user.is_platform_admin,
        ),
    )
    role = await session.scalar(
        select(Role).where(
            Role.id == invitation.role_id,
            (Role.tenant_id == invitation.tenant_id) | (Role.tenant_id.is_(None)),
        )
    )
    if role is None:
        raise AppError(
            code="invalid_or_expired_invitation",
            message="The invitation is invalid or expired",
            status_code=400,
        )
    target = await resolve_role_target(
        session,
        tenant_id=invitation.tenant_id,
        role=role,
        company_id=invitation.company_id,
        branch_id=invitation.branch_id,
    )
    await validate_inviter_authority(
        session,
        user_id=invitation.created_by_user_id,
        tenant_id=invitation.tenant_id,
        role=role,
        target=target,
    )
    membership = await session.scalar(
        select(Membership).where(
            Membership.tenant_id == invitation.tenant_id,
            Membership.user_id == auth.user.id,
        )
    )
    if membership is None:
        membership = Membership(
            id=uuid4(),
            tenant_id=invitation.tenant_id,
            user_id=auth.user.id,
            status="active",
            joined_at=now,
            version=1,
        )
        session.add(membership)
        await session.flush()
    elif membership.status in {"pending", "suspended"}:
        membership.status = "active"
        membership.joined_at = now
        membership.version += 1
    elif membership.status == "revoked":
        raise AppError(code="membership_revoked", message="Membership is revoked", status_code=403)

    existing_assignment = await session.scalar(
        select(RoleAssignment).where(
            RoleAssignment.membership_id == membership.id,
            RoleAssignment.role_id == invitation.role_id,
            RoleAssignment.company_id == invitation.company_id,
            RoleAssignment.branch_id == invitation.branch_id,
        )
    )
    if existing_assignment is None:
        session.add(
            RoleAssignment(
                id=uuid4(),
                tenant_id=invitation.tenant_id,
                membership_id=membership.id,
                role_id=invitation.role_id,
                company_id=invitation.company_id,
                branch_id=invitation.branch_id,
                assigned_by_user_id=invitation.created_by_user_id,
            )
        )
    invitation.status = "accepted"
    invitation.accepted_at = now
    invitation.version += 1
    auth.session.active_tenant_id = invitation.tenant_id
    auth.session.active_company_id = invitation.company_id
    auth.session.active_branch_id = invitation.branch_id
    await append_audit_event(
        session,
        AuditRecord(
            action="invitation.accepted",
            category="identity",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=invitation.tenant_id,
            company_id=invitation.company_id,
            branch_id=invitation.branch_id,
            resource_type="invitation",
            resource_id=str(invitation.id),
            correlation_id=correlation_id,
        ),
    )
    return membership


async def update_economic_group(
    session: AsyncSession,
    *,
    auth: AuthContext,
    group_id: UUID,
    name: str | None,
    status: str | None,
    expected_version: int,
    correlation_id: str | None,
) -> EconomicGroup:
    tenant_id = require_tenant_wide_permission(auth, "company.update")
    group = await session.scalar(
        select(EconomicGroup)
        .where(EconomicGroup.id == group_id, EconomicGroup.tenant_id == tenant_id)
        .with_for_update()
    )
    if group is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    if group.version != expected_version:
        raise AppError(code="version_conflict", message="Resource was modified", status_code=409)
    changed: list[str] = []
    if name is not None and name != group.name:
        group.name = name
        changed.append("name")
    if status is not None and status != group.status:
        group.status = status
        changed.append("status")
    group.version += 1
    await append_audit_event(
        session,
        AuditRecord(
            action="economic_group.updated",
            category="organization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            resource_type="economic_group",
            resource_id=str(group.id),
            correlation_id=correlation_id,
            changed_fields=changed,
        ),
    )
    return group


async def archive_company(
    session: AsyncSession,
    *,
    auth: AuthContext,
    company_id: UUID,
    expected_version: int,
    correlation_id: str | None,
) -> Company:
    company = await update_company(
        session,
        auth=auth,
        company_id=company_id,
        legal_name=None,
        trade_name=None,
        status="archived",
        expected_version=expected_version,
        correlation_id=correlation_id,
        permission_key="company.delete",
    )
    await append_audit_event(
        session,
        AuditRecord(
            action="company.archived",
            category="organization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=company.tenant_id,
            company_id=company.id,
            resource_type="company",
            resource_id=str(company.id),
            correlation_id=correlation_id,
        ),
    )
    return company


async def archive_branch(
    session: AsyncSession,
    *,
    auth: AuthContext,
    branch_id: UUID,
    expected_version: int,
    correlation_id: str | None,
) -> Branch:
    branch = await update_branch(
        session,
        auth=auth,
        branch_id=branch_id,
        name=None,
        status="archived",
        expected_version=expected_version,
        correlation_id=correlation_id,
        permission_key="branch.delete",
    )
    await append_audit_event(
        session,
        AuditRecord(
            action="branch.archived",
            category="organization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=branch.tenant_id,
            company_id=branch.company_id,
            branch_id=branch.id,
            resource_type="branch",
            resource_id=str(branch.id),
            correlation_id=correlation_id,
        ),
    )
    return branch


async def update_team(
    session: AsyncSession,
    *,
    auth: AuthContext,
    team_id: UUID,
    name: str | None,
    description: str | None,
    expected_version: int,
    correlation_id: str | None,
) -> Team:
    tenant_id = require_tenant_wide_permission(auth, "team.update")
    team = await session.scalar(
        select(Team).where(Team.id == team_id, Team.tenant_id == tenant_id).with_for_update()
    )
    if team is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    if team.version != expected_version:
        raise AppError(code="version_conflict", message="Resource was modified", status_code=409)
    changed: list[str] = []
    if name is not None and name != team.name:
        team.name = name
        changed.append("name")
    if description is not None and description != team.description:
        team.description = description
        changed.append("description")
    team.version += 1
    await append_audit_event(
        session,
        AuditRecord(
            action="team.updated",
            category="organization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            resource_type="team",
            resource_id=str(team.id),
            correlation_id=correlation_id,
            changed_fields=changed,
        ),
    )
    return team


async def delete_team(
    session: AsyncSession,
    *,
    auth: AuthContext,
    team_id: UUID,
    correlation_id: str | None,
) -> None:
    tenant_id = require_tenant_wide_permission(auth, "team.delete")
    team = await session.scalar(
        select(Team).where(Team.id == team_id, Team.tenant_id == tenant_id).with_for_update()
    )
    if team is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    await session.delete(team)
    await append_audit_event(
        session,
        AuditRecord(
            action="team.deleted",
            category="organization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            resource_type="team",
            resource_id=str(team.id),
            correlation_id=correlation_id,
        ),
    )


async def remove_team_member(
    session: AsyncSession,
    *,
    auth: AuthContext,
    team_id: UUID,
    membership_id: UUID,
    correlation_id: str | None,
) -> None:
    tenant_id = require_tenant_wide_permission(auth, "team.update")
    link = await session.scalar(
        select(TeamMembership).where(
            TeamMembership.team_id == team_id,
            TeamMembership.membership_id == membership_id,
            TeamMembership.tenant_id == tenant_id,
        )
    )
    if link is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    await session.delete(link)
    await append_audit_event(
        session,
        AuditRecord(
            action="team.member_removed",
            category="organization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            resource_type="team",
            resource_id=str(team_id),
            correlation_id=correlation_id,
            metadata={"membership_id": str(membership_id)},
        ),
    )


async def revoke_invitation_record(
    session: AsyncSession,
    *,
    auth: AuthContext,
    invitation_id: UUID,
    correlation_id: str | None,
) -> Invitation:
    tenant_id = require_tenant_context(auth)
    invitation = await session.scalar(
        select(Invitation)
        .where(Invitation.id == invitation_id, Invitation.tenant_id == tenant_id)
        .with_for_update()
    )
    if invitation is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    role = await session.scalar(
        select(Role).where(
            Role.id == invitation.role_id,
            (Role.tenant_id == tenant_id) | (Role.tenant_id.is_(None)),
        )
    )
    if role is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    target = await resolve_role_target(
        session,
        tenant_id=tenant_id,
        role=role,
        company_id=invitation.company_id,
        branch_id=invitation.branch_id,
    )
    await validate_role_delegation(
        session,
        auth=auth,
        role=role,
        target=target,
        authority_permission="user.invite",
    )
    if invitation.status == "accepted":
        raise AppError(
            code="invitation_already_accepted",
            message="Invitation already accepted",
            status_code=409,
        )
    if invitation.status != "revoked":
        invitation.status = "revoked"
        invitation.revoked_at = datetime.now(UTC)
        invitation.version += 1
    await append_audit_event(
        session,
        AuditRecord(
            action="invitation.revoked",
            category="identity",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            company_id=invitation.company_id,
            branch_id=invitation.branch_id,
            resource_type="invitation",
            resource_id=str(invitation.id),
            correlation_id=correlation_id,
        ),
    )
    return invitation


async def resend_invitation(
    session: AsyncSession,
    *,
    auth: AuthContext,
    invitation_id: UUID,
    correlation_id: str | None,
    settings: Settings | None = None,
) -> tuple[Invitation, EmailCommand]:
    config = settings or get_settings()
    tenant_id = require_tenant_context(auth)
    invitation = await session.scalar(
        select(Invitation)
        .where(Invitation.id == invitation_id, Invitation.tenant_id == tenant_id)
        .with_for_update()
    )
    if invitation is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    role = await session.scalar(
        select(Role).where(
            Role.id == invitation.role_id,
            (Role.tenant_id == tenant_id) | (Role.tenant_id.is_(None)),
        )
    )
    if role is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    target = await resolve_role_target(
        session,
        tenant_id=tenant_id,
        role=role,
        company_id=invitation.company_id,
        branch_id=invitation.branch_id,
    )
    await validate_role_delegation(
        session,
        auth=auth,
        role=role,
        target=target,
        authority_permission="user.invite",
    )
    if invitation.status == "accepted":
        raise AppError(
            code="invitation_already_accepted",
            message="Invitation already accepted",
            status_code=409,
        )
    now = datetime.now(UTC)
    raw_token = generate_token()
    invitation.token_hash = hash_one_time_token(raw_token, config)
    invitation.status = "pending"
    invitation.expires_at = now + timedelta(seconds=config.invitation_ttl_seconds)
    invitation.revoked_at = None
    invitation.version += 1
    invitation.created_by_user_id = auth.user.id
    await append_audit_event(
        session,
        AuditRecord(
            action="invitation.resent",
            category="identity",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            company_id=invitation.company_id,
            branch_id=invitation.branch_id,
            resource_type="invitation",
            resource_id=str(invitation.id),
            correlation_id=correlation_id,
        ),
    )
    return invitation, invitation_email(
        invitation.normalized_email, raw_token, str(invitation.id), config
    )
