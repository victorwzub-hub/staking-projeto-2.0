from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import cast

from pharma_api.domain.diagnostics.actions import ACTION_DOMAINS, ACTION_PRIORITIES, ACTION_STATUSES
from pharma_api.domain.diagnostics.conditions import SEVERITIES
from pharma_api.infrastructure.db.base import Base
from pharma_api.infrastructure.db.models import diagnostics as diagnostics_models
from pharma_api.infrastructure.db.models.diagnostics import (
    ACTION_CATALOG_STATUSES,
    HUMAN_REVIEW_EXECUTION_MODE,
    PUBLICATION_SOURCES,
    RULE_LIFECYCLE_STATUSES,
    RULE_OWNERSHIP_TYPES,
    RULE_SCOPE_TYPES,
    RULE_VERSION_POLICIES,
    RULE_VERSION_STATUSES,
)
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, Table, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import AddConstraint, CreateIndex, CreateTable

DIAGNOSTIC_TABLE_NAMES = {
    "diagnostic_rule_definitions",
    "diagnostic_rule_versions",
    "diagnostic_action_catalog_snapshots",
    "diagnostic_action_catalog_entries",
    "diagnostic_rule_configurations",
}


def _table(name: str) -> Table:
    return Base.metadata.tables[name]


def _named_constraints(table: Table) -> dict[str, object]:
    return {
        cast(str, constraint.name): constraint
        for constraint in table.constraints
        if constraint.name is not None
    }


def _named_checks(table: Table) -> dict[str, str]:
    return {
        cast(str, constraint.name): str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name is not None
    }


def _named_indexes(table: Table) -> dict[str, Index]:
    return {index.name: index for index in table.indexes if index.name is not None}


def _unique_columns(table: Table) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _foreign_key_signatures(table: Table) -> dict[str, tuple[tuple[str, ...], tuple[str, ...]]]:
    return {
        cast(str, constraint.name): (
            tuple(column.name for column in constraint.columns),
            tuple(element.target_fullname for element in constraint.elements),
        )
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint) and constraint.name is not None
    }


def _all_foreign_key_signatures(
    table: Table,
) -> set[tuple[tuple[str, ...], tuple[str, ...]]]:
    return {
        (
            tuple(column.name for column in constraint.columns),
            tuple(element.target_fullname for element in constraint.elements),
        )
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }


def _named_foreign_key_ondelete(table: Table) -> dict[str, str | None]:
    return {
        cast(str, constraint.name): constraint.ondelete
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint) and constraint.name is not None
    }


def _source(module: ModuleType) -> str:
    module_file = module.__file__
    assert module_file is not None
    return Path(module_file).read_text(encoding="utf-8")


def test_all_diagnostic_tables_are_registered_in_base_metadata() -> None:
    importlib.import_module("pharma_api.infrastructure.db.all_models")

    assert set(Base.metadata.tables) >= DIAGNOSTIC_TABLE_NAMES


def test_table_constraint_and_index_names_are_deterministic() -> None:
    expected_constraints = {
        "diagnostic_rule_definitions": {
            "uq_diagnostic_rule_definitions_id_ownership",
            "uq_diagnostic_rule_definitions_tenant_id_ownership",
            "ck_diagnostic_rule_definitions_domain",
            "ck_diagnostic_rule_definitions_ownership_type",
            "ck_diagnostic_rule_definitions_ownership",
            "ck_diagnostic_rule_definitions_lifecycle_status",
            "ck_diagnostic_rule_definitions_code",
            "ck_diagnostic_rule_definitions_current_version",
            "fk_diagnostic_rule_definitions_current_version",
        },
        "diagnostic_rule_versions": {
            "uq_diagnostic_rule_versions_definition_version",
            "ck_diagnostic_rule_versions_version_number",
            "ck_diagnostic_rule_versions_status",
            "ck_diagnostic_rule_versions_publication_source",
            "ck_diagnostic_rule_versions_period",
            "ck_diagnostic_rule_versions_publication",
            "ck_diagnostic_rule_versions_condition_hash",
            "ck_diagnostic_rule_versions_definition_hash",
            "ck_diagnostic_rule_versions_condition_document",
            "ck_diagnostic_rule_versions_kpi_codes",
            "ck_diagnostic_rule_versions_action_codes",
            "ck_diagnostic_rule_versions_controls",
            "ck_diagnostic_rule_versions_evidence_metadata",
            "ck_diagnostic_rule_versions_hypothesis_metadata",
        },
        "diagnostic_action_catalog_snapshots": {
            "uq_diagnostic_action_catalog_snapshots_version",
            "uq_diagnostic_action_catalog_snapshots_hash",
            "ck_diagnostic_action_catalog_snapshots_version",
            "ck_diagnostic_action_catalog_snapshots_status",
            "ck_diagnostic_action_catalog_snapshots_hash",
            "ck_diagnostic_action_catalog_snapshots_period",
            "ck_diagnostic_action_catalog_snapshots_publication",
            "ck_diagnostic_action_catalog_snapshots_current",
        },
        "diagnostic_action_catalog_entries": {
            "uq_diagnostic_action_catalog_entries_snapshot_code",
            "ck_diagnostic_action_catalog_entries_version",
            "ck_diagnostic_action_catalog_entries_domain",
            "ck_diagnostic_action_catalog_entries_priority",
            "ck_diagnostic_action_catalog_entries_status",
            "ck_diagnostic_action_catalog_entries_code",
            "ck_diagnostic_action_catalog_entries_period",
            "ck_diagnostic_action_catalog_entries_definition_hash",
            "ck_diagnostic_action_catalog_entries_snapshot",
            "ck_diagnostic_action_catalog_entries_execution_mode",
            "ck_diagnostic_action_catalog_entries_human_review",
            "ck_diagnostic_action_catalog_entries_snapshot_execution_mode",
            "ck_diagnostic_action_catalog_entries_no_financial_execution",
        },
        "diagnostic_rule_configurations": {
            "uq_diagnostic_rule_configurations_tenant_id",
            "fk_diagnostic_rule_configurations_company_same_tenant",
            "fk_diagnostic_rule_configurations_branch_same_tenant",
            "fk_diagnostic_rule_configurations_rule_ownership",
            "fk_diagnostic_rule_configurations_tenant_rule",
            "fk_diagnostic_rule_configurations_selected_version",
            "ck_diagnostic_rule_configurations_scope_type",
            "ck_diagnostic_rule_configurations_scope",
            "ck_diagnostic_rule_configurations_rule_ownership_type",
            "ck_diagnostic_rule_configurations_rule_ownership",
            "ck_diagnostic_rule_configurations_version_policy",
            "ck_diagnostic_rule_configurations_version_selection",
            "ck_diagnostic_rule_configurations_selected_version",
            "ck_diagnostic_rule_configurations_cooldown",
            "ck_diagnostic_rule_configurations_minimum_severity",
            "ck_diagnostic_rule_configurations_period",
        },
    }
    expected_indexes = {
        "diagnostic_rule_definitions": {
            "uq_diagnostic_rule_definitions_system_code",
            "uq_diagnostic_rule_definitions_tenant_code",
            "ix_diagnostic_rule_definitions_catalog",
        },
        "diagnostic_rule_versions": {
            "ix_diagnostic_rule_versions_catalog",
            "ix_diagnostic_rule_versions_effective",
        },
        "diagnostic_action_catalog_snapshots": {
            "uq_diagnostic_action_catalog_snapshots_current",
            "ix_diagnostic_action_catalog_snapshots_status",
        },
        "diagnostic_action_catalog_entries": {
            "ix_diagnostic_action_catalog_entries_history",
            "ix_diagnostic_action_catalog_entries_catalog",
        },
        "diagnostic_rule_configurations": {
            "uq_diagnostic_rule_configurations_scope",
            "ix_diagnostic_rule_configurations_lookup",
        },
    }

    for table_name, expected in expected_constraints.items():
        assert expected <= set(_named_constraints(_table(table_name)))
    for table_name, expected in expected_indexes.items():
        assert expected == set(_named_indexes(_table(table_name)))


def test_primary_keys_and_core_foreign_keys_are_declared() -> None:
    for table_name in DIAGNOSTIC_TABLE_NAMES:
        assert tuple(column.name for column in _table(table_name).primary_key.columns) == ("id",)

    definitions = _table("diagnostic_rule_definitions")
    rule_versions = _table("diagnostic_rule_versions")
    action_entries = _table("diagnostic_action_catalog_entries")
    configurations = _table("diagnostic_rule_configurations")

    assert (("tenant_id",), ("tenants.id",)) in _all_foreign_key_signatures(definitions)
    assert {
        (("rule_definition_id",), ("diagnostic_rule_definitions.id",)),
        (("published_by_user_id",), ("users.id",)),
    } <= _all_foreign_key_signatures(rule_versions)
    assert (
        ("catalog_snapshot_id",),
        ("diagnostic_action_catalog_snapshots.id",),
    ) in _all_foreign_key_signatures(action_entries)
    assert (("tenant_id",), ("tenants.id",)) in _all_foreign_key_signatures(configurations)

    assert _foreign_key_signatures(configurations) == {
        "fk_diagnostic_rule_configurations_company_same_tenant": (
            ("tenant_id", "company_id"),
            ("companies.tenant_id", "companies.id"),
        ),
        "fk_diagnostic_rule_configurations_branch_same_tenant": (
            ("tenant_id", "company_id", "branch_id"),
            ("branches.tenant_id", "branches.company_id", "branches.id"),
        ),
        "fk_diagnostic_rule_configurations_rule_ownership": (
            ("rule_definition_id", "rule_ownership_type"),
            (
                "diagnostic_rule_definitions.id",
                "diagnostic_rule_definitions.ownership_type",
            ),
        ),
        "fk_diagnostic_rule_configurations_tenant_rule": (
            ("rule_tenant_id", "rule_definition_id", "rule_ownership_type"),
            (
                "diagnostic_rule_definitions.tenant_id",
                "diagnostic_rule_definitions.id",
                "diagnostic_rule_definitions.ownership_type",
            ),
        ),
        "fk_diagnostic_rule_configurations_selected_version": (
            ("rule_definition_id", "selected_version_number"),
            (
                "diagnostic_rule_versions.rule_definition_id",
                "diagnostic_rule_versions.version_number",
            ),
        ),
    }


def test_tenant_owned_configuration_uses_same_tenant_scope_foreign_keys() -> None:
    configuration = _table("diagnostic_rule_configurations")
    signatures = _foreign_key_signatures(configuration)

    assert signatures["fk_diagnostic_rule_configurations_company_same_tenant"][0] == (
        "tenant_id",
        "company_id",
    )
    assert signatures["fk_diagnostic_rule_configurations_branch_same_tenant"][0] == (
        "tenant_id",
        "company_id",
        "branch_id",
    )
    assert ("tenant_id", "id") in _unique_columns(configuration)
    assert _named_foreign_key_ondelete(configuration) == {
        "fk_diagnostic_rule_configurations_company_same_tenant": "CASCADE",
        "fk_diagnostic_rule_configurations_branch_same_tenant": "CASCADE",
        "fk_diagnostic_rule_configurations_rule_ownership": "RESTRICT",
        "fk_diagnostic_rule_configurations_tenant_rule": "RESTRICT",
        "fk_diagnostic_rule_configurations_selected_version": "RESTRICT",
    }


def test_rule_ownership_is_structurally_separated_for_system_and_tenant_rules() -> None:
    definitions = _table("diagnostic_rule_definitions")
    configuration = _table("diagnostic_rule_configurations")
    definition_checks = _named_checks(definitions)
    configuration_checks = _named_checks(configuration)

    assert set(RULE_OWNERSHIP_TYPES) == {"system", "tenant"}
    assert "tenant_id IS NULL" in definition_checks["ck_diagnostic_rule_definitions_ownership"]
    assert "tenant_id IS NOT NULL" in definition_checks["ck_diagnostic_rule_definitions_ownership"]
    assert (
        "rule_tenant_id IS NULL"
        in configuration_checks["ck_diagnostic_rule_configurations_rule_ownership"]
    )
    assert (
        "rule_tenant_id = tenant_id"
        in configuration_checks["ck_diagnostic_rule_configurations_rule_ownership"]
    )
    assert {
        ("id", "ownership_type"),
        ("tenant_id", "id", "ownership_type"),
    } <= _unique_columns(definitions)
    current_version_fk = cast(
        ForeignKeyConstraint,
        _named_constraints(definitions)["fk_diagnostic_rule_definitions_current_version"],
    )
    assert current_version_fk.use_alter
    assert current_version_fk.ondelete == "RESTRICT"


def test_rule_code_versions_and_action_catalog_versions_are_unique() -> None:
    definitions = _table("diagnostic_rule_definitions")
    rule_versions = _table("diagnostic_rule_versions")
    action_snapshots = _table("diagnostic_action_catalog_snapshots")
    action_entries = _table("diagnostic_action_catalog_entries")

    definition_indexes = _named_indexes(definitions)
    system_code_index = definition_indexes["uq_diagnostic_rule_definitions_system_code"]
    tenant_code_index = definition_indexes["uq_diagnostic_rule_definitions_tenant_code"]
    assert system_code_index.unique
    assert tenant_code_index.unique
    assert str(system_code_index.dialect_options["postgresql"]["where"]) == "tenant_id IS NULL"
    assert str(tenant_code_index.dialect_options["postgresql"]["where"]) == "tenant_id IS NOT NULL"
    assert ("rule_definition_id", "version_number") in _unique_columns(rule_versions)
    assert ("catalog_version",) in _unique_columns(action_snapshots)
    assert ("catalog_hash",) in _unique_columns(action_snapshots)
    assert ("catalog_snapshot_id", "action_code") in _unique_columns(action_entries)
    configuration_scope_index = _named_indexes(_table("diagnostic_rule_configurations"))[
        "uq_diagnostic_rule_configurations_scope"
    ]
    assert configuration_scope_index.unique
    assert configuration_scope_index.dialect_options["postgresql"]["nulls_not_distinct"] is True


def test_configuration_scope_and_version_policy_are_closed_and_coherent() -> None:
    checks = _named_checks(_table("diagnostic_rule_configurations"))

    for scope_type in RULE_SCOPE_TYPES:
        assert repr(scope_type) in checks["ck_diagnostic_rule_configurations_scope_type"]
    scope_check = checks["ck_diagnostic_rule_configurations_scope"]
    assert "scope_type = 'tenant' AND company_id IS NULL AND branch_id IS NULL" in scope_check
    assert "scope_type = 'company' AND company_id IS NOT NULL AND branch_id IS NULL" in scope_check
    assert (
        "scope_type = 'branch' AND company_id IS NOT NULL AND branch_id IS NOT NULL" in scope_check
    )
    for policy in RULE_VERSION_POLICIES:
        assert repr(policy) in checks["ck_diagnostic_rule_configurations_version_policy"]
    selection_check = checks["ck_diagnostic_rule_configurations_version_selection"]
    assert "follow_published" in selection_check
    assert "selected_version_number IS NULL" in selection_check
    assert "pinned" in selection_check
    assert "selected_version_number IS NOT NULL" in selection_check


def test_closed_domain_status_severity_priority_and_publication_checks_match_catalogs() -> None:
    definition_checks = _named_checks(_table("diagnostic_rule_definitions"))
    version_checks = _named_checks(_table("diagnostic_rule_versions"))
    snapshot_checks = _named_checks(_table("diagnostic_action_catalog_snapshots"))
    entry_checks = _named_checks(_table("diagnostic_action_catalog_entries"))
    configuration_checks = _named_checks(_table("diagnostic_rule_configurations"))

    for domain in ACTION_DOMAINS:
        assert repr(domain) in definition_checks["ck_diagnostic_rule_definitions_domain"]
        assert repr(domain) in entry_checks["ck_diagnostic_action_catalog_entries_domain"]
    for status in RULE_LIFECYCLE_STATUSES:
        assert repr(status) in definition_checks["ck_diagnostic_rule_definitions_lifecycle_status"]
    for status in RULE_VERSION_STATUSES:
        assert repr(status) in version_checks["ck_diagnostic_rule_versions_status"]
    for source in PUBLICATION_SOURCES:
        assert repr(source) in version_checks["ck_diagnostic_rule_versions_publication_source"]
    for status in ACTION_CATALOG_STATUSES:
        assert repr(status) in snapshot_checks["ck_diagnostic_action_catalog_snapshots_status"]
    for status in ACTION_STATUSES:
        assert repr(status) in entry_checks["ck_diagnostic_action_catalog_entries_status"]
    for priority in ACTION_PRIORITIES:
        assert str(priority) in entry_checks["ck_diagnostic_action_catalog_entries_priority"]
    for severity in SEVERITIES:
        assert (
            repr(severity)
            in configuration_checks["ck_diagnostic_rule_configurations_minimum_severity"]
        )


def test_hash_columns_require_lowercase_sha256_hex() -> None:
    rule_checks = _named_checks(_table("diagnostic_rule_versions"))
    snapshot_checks = _named_checks(_table("diagnostic_action_catalog_snapshots"))
    action_checks = _named_checks(_table("diagnostic_action_catalog_entries"))

    assert "^[0-9a-f]{64}$" in rule_checks["ck_diagnostic_rule_versions_condition_hash"]
    assert "^[0-9a-f]{64}$" in rule_checks["ck_diagnostic_rule_versions_definition_hash"]
    assert "^[0-9a-f]{64}$" in snapshot_checks["ck_diagnostic_action_catalog_snapshots_hash"]
    assert "^[0-9a-f]{64}$" in action_checks["ck_diagnostic_action_catalog_entries_definition_hash"]


def test_action_catalog_is_global_advisory_only_and_cannot_enable_financial_execution() -> None:
    snapshot = _table("diagnostic_action_catalog_snapshots")
    entry = _table("diagnostic_action_catalog_entries")
    checks = _named_checks(entry)

    assert "tenant_id" not in snapshot.c
    assert "tenant_id" not in entry.c
    assert "allows_automatic_financial_execution" not in entry.c
    assert (
        HUMAN_REVIEW_EXECUTION_MODE in checks["ck_diagnostic_action_catalog_entries_execution_mode"]
    )
    assert (
        checks["ck_diagnostic_action_catalog_entries_human_review"]
        == "requires_human_review = true"
    )
    assert (
        "allows_automatic_financial_execution"
        in checks["ck_diagnostic_action_catalog_entries_no_financial_execution"]
    )
    assert "COALESCE" in checks["ck_diagnostic_action_catalog_entries_snapshot_execution_mode"]
    assert "COALESCE" in checks["ck_diagnostic_action_catalog_entries_no_financial_execution"]
    assert "= 'false'" in checks["ck_diagnostic_action_catalog_entries_no_financial_execution"]


def test_jsonb_is_limited_to_closed_ast_controlled_lists_and_flexible_metadata() -> None:
    jsonb_columns = {
        table_name: {
            column.name for column in _table(table_name).columns if isinstance(column.type, JSONB)
        }
        for table_name in DIAGNOSTIC_TABLE_NAMES
    }

    assert jsonb_columns == {
        "diagnostic_rule_definitions": set(),
        "diagnostic_rule_versions": {
            "condition_document",
            "kpi_codes",
            "action_codes",
            "controls",
            "evidence_metadata",
            "hypothesis_metadata",
        },
        "diagnostic_action_catalog_snapshots": set(),
        "diagnostic_action_catalog_entries": {"definition_snapshot"},
        "diagnostic_rule_configurations": set(),
    }


def test_frequently_queried_fields_remain_relational() -> None:
    expected_columns = {
        "diagnostic_rule_definitions": {
            "code",
            "domain",
            "ownership_type",
            "lifecycle_status",
            "current_published_version_number",
            "enabled_by_default",
        },
        "diagnostic_rule_versions": {
            "rule_definition_id",
            "version_number",
            "status",
            "effective_from",
            "effective_to",
            "published_at",
        },
        "diagnostic_action_catalog_snapshots": {
            "catalog_version",
            "catalog_hash",
            "status",
            "is_current",
            "effective_from",
            "effective_to",
        },
        "diagnostic_action_catalog_entries": {
            "action_code",
            "action_version",
            "domain",
            "default_priority",
            "status",
            "effective_from",
            "effective_to",
        },
        "diagnostic_rule_configurations": {
            "tenant_id",
            "company_id",
            "branch_id",
            "scope_type",
            "enabled",
            "version_policy",
            "cooldown_hours",
            "minimum_severity",
            "active_from",
            "active_to",
        },
    }

    for table_name, columns in expected_columns.items():
        assert columns <= set(_table(table_name).c.keys())


def test_postgresql_ddl_compiles_for_every_new_table_constraint_and_index() -> None:
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]

    for table_name in sorted(DIAGNOSTIC_TABLE_NAMES):
        table = _table(table_name)
        create_table_sql = str(CreateTable(table).compile(dialect=dialect))
        assert f"CREATE TABLE {table_name}" in create_table_sql
        for index in sorted(table.indexes, key=lambda item: item.name or ""):
            assert str(CreateIndex(index).compile(dialect=dialect))
        for constraint in table.constraints:
            if isinstance(constraint, ForeignKeyConstraint) and constraint.use_alter:
                assert str(AddConstraint(constraint).compile(dialect=dialect))


def test_models_do_not_depend_on_unpublished_migration_or_runtime_layers() -> None:
    source = _source(diagnostics_models)

    assert "20260719_0005" not in source
    assert "alembic" not in source
    assert "pharma_api.api" not in source
    assert "pharma_api.application" not in source
    assert "pharma_worker" not in source


def test_domain_diagnostics_remains_independent_from_database_api_and_workers() -> None:
    domain_modules = (
        importlib.import_module("pharma_api.domain.diagnostics.actions"),
        importlib.import_module("pharma_api.domain.diagnostics.conditions"),
    )

    for module in domain_modules:
        source = _source(module)
        assert "pharma_api.infrastructure" not in source
        assert "pharma_api.api" not in source
        assert "pharma_api.application" not in source
        assert "pharma_worker" not in source
