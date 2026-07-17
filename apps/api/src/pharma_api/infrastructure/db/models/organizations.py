from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pharma_api.infrastructure.db.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionMixin,
)


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(
            "status IN ('onboarding','active','suspended','archived')", name="ck_tenants_status"
        ),
        Index("ix_tenants_status", "status"),
    )

    name: Mapped[str] = mapped_column(String(180), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="onboarding")
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class EconomicGroup(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "economic_groups"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_economic_groups_tenant_name"),
        UniqueConstraint("tenant_id", "id", name="uq_economic_groups_tenant_id_id"),
        CheckConstraint(
            "status IN ('active','inactive','archived')", name="ck_economic_groups_status"
        ),
        Index("ix_economic_groups_tenant", "tenant_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")


class Company(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_companies_tenant_slug"),
        UniqueConstraint("tenant_id", "id", name="uq_companies_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "economic_group_id"],
            ["economic_groups.tenant_id", "economic_groups.id"],
            ondelete="RESTRICT",
            name="fk_companies_economic_group_same_tenant",
            use_alter=True,
        ),
        CheckConstraint("status IN ('active','inactive','archived')", name="ck_companies_status"),
        Index("ix_companies_tenant", "tenant_id"),
        Index("ix_companies_economic_group", "economic_group_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    economic_group_id: Mapped[UUID | None] = mapped_column()
    legal_name: Mapped[str] = mapped_column(String(220), nullable=False)
    trade_name: Mapped[str] = mapped_column(String(180), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")


class Branch(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "branches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "slug", name="uq_branches_company_slug"),
        UniqueConstraint("tenant_id", "id", name="uq_branches_tenant_id_id"),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_branches_tenant_company_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_branches_company_same_tenant",
        ),
        CheckConstraint("status IN ('active','inactive','archived')", name="ck_branches_status"),
        Index("ix_branches_tenant_company", "tenant_id", "company_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),
        UniqueConstraint("tenant_id", "id", name="uq_memberships_tenant_id_id"),
        CheckConstraint(
            "status IN ('pending','active','suspended','revoked')", name="ck_memberships_status"
        ),
        Index("ix_memberships_user_status", "user_id", "status"),
        Index("ix_memberships_tenant_status", "tenant_id", "status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    title: Mapped[str | None] = mapped_column(String(120))
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Team(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_teams_tenant_name"),
        UniqueConstraint("tenant_id", "id", name="uq_teams_tenant_id_id"),
        Index("ix_teams_tenant", "tenant_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))


class TeamMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "team_memberships"
    __table_args__ = (
        UniqueConstraint("team_id", "membership_id", name="uq_team_memberships_pair"),
        ForeignKeyConstraint(
            ["tenant_id", "team_id"],
            ["teams.tenant_id", "teams.id"],
            ondelete="CASCADE",
            name="fk_team_memberships_team_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["memberships.tenant_id", "memberships.id"],
            ondelete="CASCADE",
            name="fk_team_memberships_membership_same_tenant",
        ),
        Index("ix_team_memberships_tenant", "tenant_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    team_id: Mapped[UUID] = mapped_column()
    membership_id: Mapped[UUID] = mapped_column()


class OnboardingProgress(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "onboarding_progress"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_onboarding_progress_user"),
        CheckConstraint("status IN ('started','completed','failed')", name="ck_onboarding_status"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="started")
    current_step: Mapped[str] = mapped_column(String(80), nullable=False, default="account")
    data_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
