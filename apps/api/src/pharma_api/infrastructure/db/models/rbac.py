from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pharma_api.infrastructure.db.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionMixin,
)


class Permission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "permissions"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('platform','tenant','company','branch')", name="ck_permissions_scope"
        ),
        Index("ix_permissions_scope", "scope"),
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    scope: Mapped[str] = mapped_column(String(24), nullable=False)
    description: Mapped[str] = mapped_column(String(400), nullable=False)
    catalog_version: Mapped[int] = mapped_column(nullable=False, default=1)


class Role(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint("scope IN ('platform','tenant','company','branch')", name="ck_roles_scope"),
        CheckConstraint(
            "(is_system = true AND tenant_id IS NULL) OR "
            "(is_system = false AND tenant_id IS NOT NULL)",
            name="ck_roles_ownership",
        ),
        Index("ix_roles_tenant", "tenant_id"),
        Index(
            "uq_roles_system_slug",
            "slug",
            unique=True,
            postgresql_where=text("tenant_id IS NULL"),
        ),
        Index(
            "uq_roles_tenant_slug",
            "tenant_id",
            "slug",
            unique=True,
            postgresql_where=text("tenant_id IS NOT NULL"),
        ),
    )

    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    scope: Mapped[str] = mapped_column(String(24), nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_editable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(String(400))


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class RoleAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "role_assignments"
    __table_args__ = (
        Index(
            "uq_role_assignments_scope",
            "membership_id",
            "role_id",
            "company_id",
            "branch_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["memberships.tenant_id", "memberships.id"],
            ondelete="CASCADE",
            name="fk_role_assignments_membership_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_role_assignments_company_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_role_assignments_branch_same_tenant",
        ),
        Index("ix_role_assignments_tenant_membership", "tenant_id", "membership_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    membership_id: Mapped[UUID] = mapped_column()
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"))
    company_id: Mapped[UUID | None] = mapped_column()
    branch_id: Mapped[UUID | None] = mapped_column()
    assigned_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
