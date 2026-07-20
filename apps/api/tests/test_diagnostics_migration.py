from __future__ import annotations

import importlib.util
import io
import re
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

from alembic.migration import MigrationContext
from alembic.operations import Operations

import pharma_api.infrastructure.db.all_models  # noqa: F401
from pharma_api.cli import migrate
from pharma_api.domain.diagnostics.actions import ACTION_CATALOG
from pharma_api.infrastructure.db.base import Base
from pharma_api.infrastructure.db.migration_data import diagnostic_action_catalog_v1 as seed

MIGRATION_PATH = (
    Path(__file__).parents[1] / "alembic" / "versions" / "20260719_0005_diagnostics_rules_engine.py"
)
EXPECTED_TABLES = {
    "diagnostic_rule_definitions",
    "diagnostic_rule_versions",
    "diagnostic_action_catalog_snapshots",
    "diagnostic_action_catalog_entries",
    "diagnostic_rule_configurations",
    "diagnostic_evaluation_runs",
    "diagnostic_findings",
    "diagnostic_evidences",
    "diagnostic_hypotheses",
    "diagnostic_hypothesis_evidences",
    "diagnostic_action_recommendations",
    "diagnostic_suppressions",
    "diagnostic_incidents",
    "diagnostic_incident_memberships",
}


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("diagnostics_migration_0005", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _compile_offline(function_name: str) -> str:
    migration = _load_migration()
    output = io.StringIO()
    context = MigrationContext.configure(
        url="postgresql://",
        opts={"as_sql": True, "output_buffer": output},
    )
    migration.__dict__["op"] = Operations(context)
    if function_name == "upgrade":
        migration.__dict__["_seed_permissions"] = lambda: None
        migration.__dict__["_seed_action_catalog"] = lambda: None
    cast(Callable[[], None], getattr(migration, function_name))()
    return output.getvalue()


def test_revision_chain_and_exact_table_set() -> None:
    migration = _load_migration()
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert migration.revision == "20260719_0005"
    assert migration.down_revision == "20260718_0004"
    assert (
        set(re.findall(r"op\.create_table\(\s*[\"\']([^\"\']+)[\"\']", source)) == EXPECTED_TABLES
    )


def test_frozen_action_seed_matches_approved_domain_catalog() -> None:
    approved = tuple(action.as_dict() for action in ACTION_CATALOG)

    assert seed.ACTION_COUNT == 30
    assert approved == seed.ACTION_CATALOG_DEFINITIONS
    assert seed.deterministic_hash(approved) == seed.CATALOG_HASH
    assert len(seed.CATALOG_HASH) == 64
    assert len({row["id"] for row in seed.iter_entry_rows()}) == seed.ACTION_COUNT
    assert all(len(str(row["definition_hash"])) == 64 for row in seed.iter_entry_rows())
    assert all(row["requires_human_review"] is True for row in seed.iter_entry_rows())
    assert all(
        row["definition_snapshot"]["allows_automatic_financial_execution"] is False
        for row in seed.iter_entry_rows()
    )


def test_upgrade_ddl_compiles_for_postgresql() -> None:
    sql = _compile_offline("upgrade")

    for table in EXPECTED_TABLES:
        assert f"CREATE TABLE {table}" in sql
    assert "ALTER TABLE diagnostic_rule_definitions ADD CONSTRAINT" in sql
    assert "fk_diagnostic_rule_definitions_current_version" in sql
    assert "NULLS NOT DISTINCT" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql


def test_migration_contains_every_named_model_constraint_and_index() -> None:
    sql = _compile_offline("upgrade")

    for table_name in EXPECTED_TABLES:
        table = Base.metadata.tables[table_name]
        expected_names: set[str] = set()
        for constraint in table.constraints:
            if isinstance(constraint.name, str):
                expected_names.add(constraint.name)
        for index in table.indexes:
            if isinstance(index.name, str):
                expected_names.add(index.name)
        assert expected_names
        assert all(name in sql for name in expected_names)


def test_downgrade_ddl_compiles_and_removes_cycle_first() -> None:
    sql = _compile_offline("downgrade")

    cycle = "ALTER TABLE diagnostic_rule_definitions DROP CONSTRAINT"
    rule_versions = "DROP TABLE diagnostic_rule_versions"
    assert cycle in sql
    assert sql.index(cycle) < sql.index(rule_versions)
    assert sql.index("DROP POLICY") < sql.index("DROP TABLE")


def test_rls_policy_shapes_cover_tenant_mixed_and_global_tables() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "diagnostic_rule_definitions_select_policy" in _compile_offline("upgrade")
    assert "diagnostic_rule_versions_select_policy" in _compile_offline("upgrade")
    assert "definition.tenant_id IS NULL" in source
    assert "definition.tenant_id = NULLIF(current_setting('app.current_tenant_id'" in source
    assert "diagnostic_action_catalog_snapshots_select_policy" in _compile_offline("upgrade")
    assert "REVOKE INSERT, UPDATE, DELETE" in source
    compiled = _compile_offline("upgrade")
    for table in cast(tuple[str, ...], _load_migration().TENANT_TABLES):
        assert f'CREATE POLICY "{table}_tenant_policy"' in compiled


def test_permissions_use_only_existing_system_role_slugs() -> None:
    migration = _load_migration()
    expected_roles = {
        "tenant_owner",
        "tenant_admin",
        "company_admin",
        "branch_manager",
        "analyst",
        "consultant",
        "accountant",
        "viewer",
    }

    assert set(migration.ROLE_PERMISSION_GRANTS) == expected_roles
    assert {key for key, _, _ in migration.DIAGNOSTIC_PERMISSIONS} == {
        "diagnostics.view",
        "diagnostics.evaluate",
        "diagnostics.rules.manage",
        "diagnostics.suppress",
        "diagnostics.incidents.manage",
    }


def test_runtime_grant_path_protects_global_catalog_tables() -> None:
    protected = set(migrate._PROTECTED_RUNTIME_TABLES)
    prepare_source = (
        Path(__file__).parents[3] / "scripts" / "prepare-integration-database.py"
    ).read_text(encoding="utf-8")

    assert "diagnostic_action_catalog_snapshots" in protected
    assert "diagnostic_action_catalog_entries" in protected
    assert "diagnostic_action_catalog_snapshots" in prepare_source
    assert "diagnostic_action_catalog_entries" in prepare_source


def test_no_later_migration_was_created() -> None:
    migration_dir = MIGRATION_PATH.parent
    revisions = sorted(path.name for path in migration_dir.glob("20260719_*.py"))

    assert revisions == [MIGRATION_PATH.name]
