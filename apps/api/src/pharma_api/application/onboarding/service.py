from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.audit.service import AuditRecord, append_audit_event
from pharma_api.application.auth.types import AuthContext
from pharma_api.core.errors import AppError
from pharma_api.infrastructure.db.context import RLSContext, apply_rls_context
from pharma_api.infrastructure.db.models.operations import ConsentRecord, TermsVersion
from pharma_api.infrastructure.db.models.organizations import (
    Branch,
    Company,
    EconomicGroup,
    Membership,
    OnboardingProgress,
    Tenant,
)
from pharma_api.infrastructure.db.models.rbac import Role, RoleAssignment


@dataclass(frozen=True, slots=True)
class OnboardingResult:
    tenant_id: UUID
    company_id: UUID
    branch_id: UUID
    membership_id: UUID


async def get_progress(session: AsyncSession, auth: AuthContext) -> OnboardingProgress:
    progress = await session.scalar(
        select(OnboardingProgress).where(OnboardingProgress.user_id == auth.user.id)
    )
    if progress is None:
        progress = OnboardingProgress(
            id=uuid4(),
            user_id=auth.user.id,
            status="started",
            current_step="organization",
            data_json={},
            version=1,
        )
        session.add(progress)
    return progress


async def complete_onboarding(
    session: AsyncSession,
    *,
    auth: AuthContext,
    tenant_name: str,
    tenant_slug: str,
    economic_group_name: str | None,
    company_legal_name: str,
    company_trade_name: str,
    company_slug: str,
    branch_name: str,
    branch_slug: str,
    terms_version_id: UUID,
    accept_terms: bool,
    correlation_id: str | None,
    ip_hash: str | None,
) -> OnboardingResult:
    if not accept_terms:
        raise AppError(
            code="terms_required", message="Terms acceptance is required", status_code=400
        )
    if auth.user.email_verified_at is None:
        raise AppError(
            code="email_not_verified", message="Email verification is required", status_code=403
        )

    progress = await session.scalar(
        select(OnboardingProgress)
        .where(OnboardingProgress.user_id == auth.user.id)
        .with_for_update()
    )
    if progress is not None and progress.status == "completed":
        data = progress.data_json
        try:
            return OnboardingResult(
                tenant_id=UUID(data["tenant_id"]),
                company_id=UUID(data["company_id"]),
                branch_id=UUID(data["branch_id"]),
                membership_id=UUID(data["membership_id"]),
            )
        except (KeyError, ValueError) as exc:
            raise AppError(
                code="onboarding_state_invalid",
                message="Onboarding state is inconsistent",
                status_code=500,
            ) from exc

    existing_membership = await session.scalar(
        select(Membership).where(Membership.user_id == auth.user.id, Membership.status == "active")
    )
    if existing_membership is not None:
        raise AppError(
            code="onboarding_already_has_membership",
            message="The account already belongs to an organization",
            status_code=409,
        )

    terms = await session.scalar(
        select(TermsVersion).where(
            TermsVersion.id == terms_version_id,
            TermsVersion.is_active.is_(True),
            TermsVersion.effective_at <= datetime.now(UTC),
        )
    )
    if terms is None:
        raise AppError(
            code="terms_version_invalid", message="Terms version is invalid", status_code=400
        )

    now = datetime.now(UTC)
    tenant = Tenant(
        id=uuid4(),
        name=tenant_name,
        slug=tenant_slug,
        status="onboarding",
        created_by_user_id=auth.user.id,
        version=1,
    )
    session.add(tenant)
    await session.flush()
    await apply_rls_context(
        session,
        RLSContext(
            user_id=auth.user.id,
            tenant_id=tenant.id,
            is_platform_admin=auth.user.is_platform_admin,
        ),
    )

    group: EconomicGroup | None = None
    if economic_group_name:
        group = EconomicGroup(
            id=uuid4(),
            tenant_id=tenant.id,
            name=economic_group_name,
            status="active",
            version=1,
        )
        session.add(group)
        await session.flush()

    company = Company(
        id=uuid4(),
        tenant_id=tenant.id,
        economic_group_id=group.id if group else None,
        legal_name=company_legal_name,
        trade_name=company_trade_name,
        slug=company_slug,
        status="active",
        version=1,
    )
    session.add(company)
    await session.flush()
    branch = Branch(
        id=uuid4(),
        tenant_id=tenant.id,
        company_id=company.id,
        name=branch_name,
        slug=branch_slug,
        status="active",
        version=1,
    )
    membership = Membership(
        id=uuid4(),
        tenant_id=tenant.id,
        user_id=auth.user.id,
        status="active",
        joined_at=now,
        version=1,
    )
    session.add_all([branch, membership])
    await session.flush()

    owner_role = await session.scalar(
        select(Role).where(Role.slug == "tenant_owner", Role.is_system.is_(True))
    )
    if owner_role is None:
        raise AppError(
            code="system_role_missing", message="System role is unavailable", status_code=500
        )
    session.add(
        RoleAssignment(
            id=uuid4(),
            tenant_id=tenant.id,
            membership_id=membership.id,
            role_id=owner_role.id,
            company_id=None,
            branch_id=None,
            assigned_by_user_id=auth.user.id,
        )
    )
    session.add(
        ConsentRecord(
            id=uuid4(),
            user_id=auth.user.id,
            tenant_id=tenant.id,
            terms_version_id=terms.id,
            accepted_at=now,
            ip_hash=ip_hash,
        )
    )

    tenant.status = "active"
    auth.session.active_tenant_id = tenant.id
    auth.session.active_company_id = company.id
    auth.session.active_branch_id = branch.id

    if progress is None:
        progress = OnboardingProgress(
            id=uuid4(),
            user_id=auth.user.id,
            version=1,
        )
        session.add(progress)
    progress.tenant_id = tenant.id
    progress.status = "completed"
    progress.current_step = "completed"
    progress.completed_at = now
    progress.data_json = {
        "tenant_id": str(tenant.id),
        "company_id": str(company.id),
        "branch_id": str(branch.id),
        "membership_id": str(membership.id),
    }
    progress.version += 1

    await append_audit_event(
        session,
        AuditRecord(
            action="onboarding.completed",
            category="onboarding",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            tenant_id=tenant.id,
            company_id=company.id,
            branch_id=branch.id,
            resource_type="tenant",
            resource_id=str(tenant.id),
            correlation_id=correlation_id,
            metadata={"terms_version": terms.version},
        ),
    )
    return OnboardingResult(
        tenant_id=tenant.id,
        company_id=company.id,
        branch_id=branch.id,
        membership_id=membership.id,
    )
