from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _migration_module() -> ModuleType:
    migration = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "20260716_0001_identity_tenancy_core.py"
    )
    spec = importlib.util.spec_from_file_location("phase2_initial_migration", migration)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tenant_roles_never_inherit_platform_administration() -> None:
    module = _migration_module()
    role_definitions = module.ROLE_DEFINITIONS

    assert role_definitions["platform_admin"][1] == ("platform.admin",)
    for role_name, (_, permissions) in role_definitions.items():
        if role_name != "platform_admin":
            assert "platform.admin" not in permissions
            assert "impersonation.start" not in permissions


def test_tenant_rls_allows_authorized_members_to_update_tenant() -> None:
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "20260716_0001_identity_tenancy_core.py"
    )
    source = migration_path.read_text()

    assert "m.status = 'active'" in source
    assert "m.user_id = {current_user}" in source


def test_database_protects_system_role_permissions_from_direct_mutation() -> None:
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "20260716_0001_identity_tenancy_core.py"
    )
    source = migration_path.read_text()

    assert "reject_system_role_permission_mutation" in source
    assert "system role permissions are immutable" in source
    assert "BEFORE INSERT OR UPDATE OR DELETE ON role_permissions" in source


def test_downgrade_removes_all_rls_policies_before_triggers_and_tables() -> None:
    module = _migration_module()
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "20260716_0001_identity_tenancy_core.py"
    )
    source = migration_path.read_text()
    downgrade_source = source[source.index("def downgrade() -> None:") :]

    assert module.RLS_POLICY_TABLES == (
        "tenants",
        "economic_groups",
        "companies",
        "branches",
        "memberships",
        "teams",
        "team_memberships",
        "roles",
        "role_permissions",
        "role_assignments",
        "invitations",
        "consent_records",
        "onboarding_progress",
        "audit_events",
    )
    assert "DROP POLICY IF EXISTS" in downgrade_source
    assert downgrade_source.index("DROP POLICY IF EXISTS") < downgrade_source.index(
        "DROP TRIGGER IF EXISTS"
    )
    assert downgrade_source.rindex("DROP TRIGGER IF EXISTS") < downgrade_source.index(
        "DROP FUNCTION IF EXISTS"
    )
    assert downgrade_source.index("DROP FUNCTION IF EXISTS") < downgrade_source.index(
        "op.drop_table(table)"
    )
