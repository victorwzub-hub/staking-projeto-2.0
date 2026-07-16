from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.audit.service import AuditRecord, append_audit_event
from pharma_api.application.auth.types import AuthContext
from pharma_api.core.errors import AppError
from pharma_api.infrastructure.db.context import RLSContext, apply_rls_context
from pharma_api.infrastructure.db.models.organizations import Branch, Company, Membership, Tenant


@dataclass(frozen=True, slots=True)
class BranchContext:
    id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class CompanyContext:
    id: UUID
    name: str
    branches: list[BranchContext]


@dataclass(frozen=True, slots=True)
class MembershipContext:
    membership_id: UUID
    tenant_id: UUID
    tenant_name: str
    status: str
    companies: list[CompanyContext]


async def list_user_contexts(session: AsyncSession, auth: AuthContext) -> list[MembershipContext]:
    await apply_rls_context(
        session,
        RLSContext(user_id=auth.user.id, is_platform_admin=auth.user.is_platform_admin),
    )
    memberships = (
        await session.scalars(
            select(Membership)
            .where(Membership.user_id == auth.user.id, Membership.status == "active")
            .order_by(Membership.created_at)
        )
    ).all()
    result: list[MembershipContext] = []
    for membership in memberships:
        await apply_rls_context(
            session,
            RLSContext(
                user_id=auth.user.id,
                tenant_id=membership.tenant_id,
                is_platform_admin=auth.user.is_platform_admin,
            ),
        )
        tenant = await session.get(Tenant, membership.tenant_id)
        if tenant is None:
            continue
        companies = (
            await session.scalars(
                select(Company)
                .where(Company.tenant_id == tenant.id, Company.status == "active")
                .order_by(Company.trade_name)
            )
        ).all()
        company_contexts: list[CompanyContext] = []
        for company in companies:
            branches = (
                await session.scalars(
                    select(Branch)
                    .where(
                        Branch.tenant_id == tenant.id,
                        Branch.company_id == company.id,
                        Branch.status == "active",
                    )
                    .order_by(Branch.name)
                )
            ).all()
            company_contexts.append(
                CompanyContext(
                    id=company.id,
                    name=company.trade_name,
                    branches=[BranchContext(id=branch.id, name=branch.name) for branch in branches],
                )
            )
        result.append(
            MembershipContext(
                membership_id=membership.id,
                tenant_id=tenant.id,
                tenant_name=tenant.name,
                status=membership.status,
                companies=company_contexts,
            )
        )
    await apply_rls_context(
        session,
        RLSContext(
            user_id=auth.user.id,
            tenant_id=auth.session.active_tenant_id,
            is_platform_admin=auth.user.is_platform_admin,
        ),
    )
    return result


async def _deny_context_switch(
    session: AsyncSession,
    *,
    auth: AuthContext,
    requested_tenant_id: UUID,
    requested_company_id: UUID | None,
    requested_branch_id: UUID | None,
    correlation_id: str | None,
    reason: str,
) -> None:
    # Restore the actor's authorized context before writing the durable denial event.
    await apply_rls_context(
        session,
        RLSContext(
            user_id=auth.user.id,
            tenant_id=auth.tenant_id,
            is_platform_admin=auth.user.is_platform_admin,
        ),
    )
    await append_audit_event(
        session,
        AuditRecord(
            action="context.switch_denied",
            category="authorization",
            outcome="denied",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=auth.tenant_id,
            company_id=auth.company_id,
            branch_id=auth.branch_id,
            resource_type="session",
            resource_id=str(auth.session.id),
            correlation_id=correlation_id,
            metadata={
                "reason": reason,
                "requested_tenant_id": str(requested_tenant_id),
                "requested_company_id": str(requested_company_id) if requested_company_id else None,
                "requested_branch_id": str(requested_branch_id) if requested_branch_id else None,
            },
        ),
    )
    await session.commit()


async def switch_context(
    session: AsyncSession,
    *,
    auth: AuthContext,
    tenant_id: UUID,
    company_id: UUID | None,
    branch_id: UUID | None,
    correlation_id: str | None,
) -> None:
    await apply_rls_context(
        session,
        RLSContext(user_id=auth.user.id, is_platform_admin=auth.user.is_platform_admin),
    )
    membership = await session.scalar(
        select(Membership).where(
            Membership.user_id == auth.user.id,
            Membership.tenant_id == tenant_id,
            Membership.status == "active",
        )
    )
    if membership is None and not auth.user.is_platform_admin:
        await _deny_context_switch(
            session,
            auth=auth,
            requested_tenant_id=tenant_id,
            requested_company_id=company_id,
            requested_branch_id=branch_id,
            correlation_id=correlation_id,
            reason="membership_not_active",
        )
        raise AppError(code="not_found", message="Resource not found", status_code=404)

    await apply_rls_context(
        session,
        RLSContext(
            user_id=auth.user.id,
            tenant_id=tenant_id,
            is_platform_admin=auth.user.is_platform_admin,
        ),
    )
    if company_id is not None:
        company = await session.scalar(
            select(Company).where(Company.id == company_id, Company.tenant_id == tenant_id)
        )
        if company is None:
            await _deny_context_switch(
                session,
                auth=auth,
                requested_tenant_id=tenant_id,
                requested_company_id=company_id,
                requested_branch_id=branch_id,
                correlation_id=correlation_id,
                reason="company_not_available",
            )
            raise AppError(code="not_found", message="Resource not found", status_code=404)
    if branch_id is not None:
        if company_id is None:
            await _deny_context_switch(
                session,
                auth=auth,
                requested_tenant_id=tenant_id,
                requested_company_id=company_id,
                requested_branch_id=branch_id,
                correlation_id=correlation_id,
                reason="company_context_required",
            )
            raise AppError(
                code="company_context_required", message="Company context required", status_code=400
            )
        branch = await session.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.tenant_id == tenant_id,
                Branch.company_id == company_id,
            )
        )
        if branch is None:
            await _deny_context_switch(
                session,
                auth=auth,
                requested_tenant_id=tenant_id,
                requested_company_id=company_id,
                requested_branch_id=branch_id,
                correlation_id=correlation_id,
                reason="branch_not_available",
            )
            raise AppError(code="not_found", message="Resource not found", status_code=404)

    previous = {
        "tenant_id": str(auth.session.active_tenant_id) if auth.session.active_tenant_id else None,
        "company_id": str(auth.session.active_company_id)
        if auth.session.active_company_id
        else None,
        "branch_id": str(auth.session.active_branch_id) if auth.session.active_branch_id else None,
    }
    auth.session.active_tenant_id = tenant_id
    auth.session.active_company_id = company_id
    auth.session.active_branch_id = branch_id
    await append_audit_event(
        session,
        AuditRecord(
            action="context.switched",
            category="authorization",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant_id,
            company_id=company_id,
            branch_id=branch_id,
            resource_type="session",
            resource_id=str(auth.session.id),
            correlation_id=correlation_id,
            metadata={"previous": previous},
        ),
    )
