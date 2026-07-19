from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import cast

from pharma_api.domain.diagnostics.actions import ACTION_DOMAINS, ACTION_PRIORITIES
from pharma_api.domain.diagnostics.conditions import SEVERITIES
from pharma_api.infrastructure.db.base import Base
from pharma_api.infrastructure.db.models import diagnostics as diagnostics_models
from pharma_api.infrastructure.db.models.diagnostics import (
    ACTION_RECOMMENDATION_STATUSES,
    DIAGNOSTIC_STATUSES,
    EVALUATION_ERROR_TYPES,
    EVALUATION_STATUSES,
    EVALUATION_TRIGGER_TYPES,
    EVIDENCE_DIRECTIONS,
    EVIDENCE_SOURCES,
    EVIDENCE_TYPES,
    HYPOTHESIS_EVIDENCE_RELATIONS,
    HYPOTHESIS_STATUSES,
    INCIDENT_STATUSES,
    RULE_SCOPE_TYPES,
    SUPPRESSION_REASONS,
    SUPPRESSION_SOURCES,
    SUPPRESSION_STATUSES,
    SUPPRESSION_TARGET_TYPES,
    SUPPRESSION_TYPES,
)
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, Table, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CreateIndex, CreateTable

OPERATIONAL_TABLE_NAMES = {
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


def _foreign_key_signatures(table: Table) -> set[tuple[tuple[str, ...], tuple[str, ...]]]:
    return {
        (
            tuple(column.name for column in constraint.columns),
            tuple(element.target_fullname for element in constraint.elements),
        )
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }


def _named_foreign_keys(table: Table) -> dict[str, ForeignKeyConstraint]:
    return {
        cast(str, constraint.name): constraint
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint) and constraint.name is not None
    }


def _source(module: ModuleType) -> str:
    module_file = module.__file__
    assert module_file is not None
    return Path(module_file).read_text(encoding="utf-8")


def test_operational_tables_are_registered_in_base_metadata() -> None:
    importlib.import_module("pharma_api.infrastructure.db.all_models")

    assert set(Base.metadata.tables) >= OPERATIONAL_TABLE_NAMES


def test_operational_constraint_and_index_names_are_deterministic() -> None:
    expected_constraints = {
        "diagnostic_evaluation_runs": {
            "uq_diagnostic_evaluation_runs_tenant_id",
            "uq_diagnostic_evaluation_runs_idempotency",
            "uq_diagnostic_evaluation_runs_tenant_scope",
            "uq_diagnostic_evaluation_runs_tenant_company",
            "uq_diagnostic_evaluation_runs_tenant_branch",
            "fk_diagnostic_evaluation_runs_company_same_tenant",
            "fk_diagnostic_evaluation_runs_branch_same_tenant",
            "ck_diagnostic_evaluation_runs_scope_type",
            "ck_diagnostic_evaluation_runs_scope",
            "ck_diagnostic_evaluation_runs_trigger_type",
            "ck_diagnostic_evaluation_runs_status",
            "ck_diagnostic_evaluation_runs_error_type",
            "ck_diagnostic_evaluation_runs_error_state",
            "ck_diagnostic_evaluation_runs_window",
            "ck_diagnostic_evaluation_runs_period",
            "ck_diagnostic_evaluation_runs_duration",
            "ck_diagnostic_evaluation_runs_data_version",
            "ck_diagnostic_evaluation_runs_counters",
        },
        "diagnostic_findings": {
            "uq_diagnostic_findings_tenant_id",
            "uq_diagnostic_findings_run_fingerprint",
            "fk_diagnostic_findings_company_same_tenant",
            "fk_diagnostic_findings_branch_same_tenant",
            "fk_diagnostic_findings_run_same_scope",
            "fk_diagnostic_findings_run_same_company",
            "fk_diagnostic_findings_run_same_branch",
            "fk_diagnostic_findings_rule_ownership",
            "fk_diagnostic_findings_tenant_rule",
            "fk_diagnostic_findings_rule_version",
            "ck_diagnostic_findings_scope_type",
            "ck_diagnostic_findings_scope",
            "ck_diagnostic_findings_domain",
            "ck_diagnostic_findings_rule_ownership_type",
            "ck_diagnostic_findings_rule_ownership",
            "ck_diagnostic_findings_status",
            "ck_diagnostic_findings_severity",
            "ck_diagnostic_findings_priority",
            "ck_diagnostic_findings_confidence",
            "ck_diagnostic_findings_affected_period",
            "ck_diagnostic_findings_observation_period",
            "ck_diagnostic_findings_occurrence_count",
            "ck_diagnostic_findings_versions",
            "ck_diagnostic_findings_fingerprint",
            "ck_diagnostic_findings_code",
            "ck_diagnostic_findings_context_snapshot",
            "ck_diagnostic_findings_lifecycle",
        },
        "diagnostic_evidences": {
            "uq_diagnostic_evidences_tenant_id",
            "uq_diagnostic_evidences_tenant_diagnostic_id",
            "uq_diagnostic_evidences_hash",
            "uq_diagnostic_evidences_order",
            "fk_diagnostic_evidences_finding_same_tenant",
            "ck_diagnostic_evidences_type",
            "ck_diagnostic_evidences_direction",
            "ck_diagnostic_evidences_source",
            "ck_diagnostic_evidences_period",
            "ck_diagnostic_evidences_versions",
            "ck_diagnostic_evidences_hash",
            "ck_diagnostic_evidences_order",
            "ck_diagnostic_evidences_detail_snapshot",
        },
        "diagnostic_hypotheses": {
            "uq_diagnostic_hypotheses_tenant_id",
            "uq_diagnostic_hypotheses_tenant_diagnostic_id",
            "uq_diagnostic_hypotheses_definition",
            "uq_diagnostic_hypotheses_rank",
            "fk_diagnostic_hypotheses_finding_same_tenant",
            "ck_diagnostic_hypotheses_code",
            "ck_diagnostic_hypotheses_status",
            "ck_diagnostic_hypotheses_confidence",
            "ck_diagnostic_hypotheses_rank",
            "ck_diagnostic_hypotheses_evidence_counts",
            "ck_diagnostic_hypotheses_definition_snapshot",
            "ck_diagnostic_hypotheses_evaluation_time",
        },
        "diagnostic_hypothesis_evidences": {
            "fk_diagnostic_hypothesis_evidences_hypothesis_same_diagnostic",
            "fk_diagnostic_hypothesis_evidences_evidence_same_diagnostic",
            "uq_diagnostic_hypothesis_evidences_order",
            "ck_diagnostic_hypothesis_evidences_relation",
            "ck_diagnostic_hypothesis_evidences_order",
        },
        "diagnostic_action_recommendations": {
            "uq_diagnostic_action_recommendations_tenant_id",
            "uq_diagnostic_action_recommendations_entry",
            "uq_diagnostic_action_recommendations_order",
            "fk_diagnostic_action_recommendations_finding_same_tenant",
            "ck_diagnostic_action_recommendations_priority",
            "ck_diagnostic_action_recommendations_status",
            "ck_diagnostic_action_recommendations_order",
            "ck_diagnostic_action_recommendations_human_review",
            "ck_diagnostic_action_recommendations_reviewed_at",
        },
        "diagnostic_suppressions": {
            "uq_diagnostic_suppressions_tenant_id",
            "fk_diagnostic_suppressions_company_same_tenant",
            "fk_diagnostic_suppressions_branch_same_tenant",
            "fk_diagnostic_suppressions_rule_ownership",
            "fk_diagnostic_suppressions_tenant_rule",
            "ck_diagnostic_suppressions_scope_type",
            "ck_diagnostic_suppressions_scope",
            "ck_diagnostic_suppressions_type",
            "ck_diagnostic_suppressions_target_type",
            "ck_diagnostic_suppressions_reason",
            "ck_diagnostic_suppressions_source",
            "ck_diagnostic_suppressions_status",
            "ck_diagnostic_suppressions_type_source",
            "ck_diagnostic_suppressions_target",
            "ck_diagnostic_suppressions_rule_ownership",
            "ck_diagnostic_suppressions_fingerprint",
            "ck_diagnostic_suppressions_period",
            "ck_diagnostic_suppressions_expiration",
            "ck_diagnostic_suppressions_lifecycle",
        },
        "diagnostic_incidents": {
            "uq_diagnostic_incidents_tenant_id",
            "uq_diagnostic_incidents_code",
            "fk_diagnostic_incidents_company_same_tenant",
            "fk_diagnostic_incidents_branch_same_tenant",
            "fk_diagnostic_incidents_primary_finding_same_tenant",
            "ck_diagnostic_incidents_scope_type",
            "ck_diagnostic_incidents_scope",
            "ck_diagnostic_incidents_domain",
            "ck_diagnostic_incidents_severity",
            "ck_diagnostic_incidents_priority",
            "ck_diagnostic_incidents_status",
            "ck_diagnostic_incidents_code",
            "ck_diagnostic_incidents_fingerprint",
            "ck_diagnostic_incidents_period",
            "ck_diagnostic_incidents_count",
            "ck_diagnostic_incidents_lifecycle",
        },
        "diagnostic_incident_memberships": {
            "fk_diagnostic_incident_memberships_incident_same_tenant",
            "fk_diagnostic_incident_memberships_finding_same_tenant",
            "uq_diagnostic_incident_memberships_order",
            "ck_diagnostic_incident_memberships_order",
        },
    }
    expected_indexes = {
        "diagnostic_evaluation_runs": {
            "ix_diagnostic_evaluation_runs_scope_created",
            "ix_diagnostic_evaluation_runs_status",
        },
        "diagnostic_findings": {
            "ix_diagnostic_findings_scope_status",
            "ix_diagnostic_findings_fingerprint",
            "ix_diagnostic_findings_rule",
        },
        "diagnostic_evidences": {
            "ix_diagnostic_evidences_finding",
            "ix_diagnostic_evidences_kpi_period",
        },
        "diagnostic_hypotheses": {"ix_diagnostic_hypotheses_finding"},
        "diagnostic_hypothesis_evidences": {"ix_diagnostic_hypothesis_evidences_evidence"},
        "diagnostic_action_recommendations": {"ix_diagnostic_action_recommendations_finding"},
        "diagnostic_suppressions": {
            "uq_diagnostic_suppressions_target_period",
            "ix_diagnostic_suppressions_active",
        },
        "diagnostic_incidents": {
            "ix_diagnostic_incidents_scope_status",
            "ix_diagnostic_incidents_fingerprint",
        },
        "diagnostic_incident_memberships": {"ix_diagnostic_incident_memberships_finding"},
    }

    for table_name, expected in expected_constraints.items():
        assert expected <= set(_named_constraints(_table(table_name)))
    for table_name, expected in expected_indexes.items():
        assert expected == set(_named_indexes(_table(table_name)))


def test_all_operational_models_are_tenant_owned() -> None:
    for table_name in OPERATIONAL_TABLE_NAMES:
        assert "tenant_id" in _table(table_name).c


def test_primary_keys_are_deterministic() -> None:
    entity_tables = OPERATIONAL_TABLE_NAMES - {
        "diagnostic_hypothesis_evidences",
        "diagnostic_incident_memberships",
    }
    for table_name in entity_tables:
        assert tuple(column.name for column in _table(table_name).primary_key.columns) == ("id",)

    assert tuple(
        column.name for column in _table("diagnostic_hypothesis_evidences").primary_key.columns
    ) == ("tenant_id", "hypothesis_id", "evidence_id")
    assert tuple(
        column.name for column in _table("diagnostic_incident_memberships").primary_key.columns
    ) == ("tenant_id", "incident_id", "diagnostic_id")


def test_scope_owned_models_use_same_tenant_company_and_branch_foreign_keys() -> None:
    expected_by_table = {
        "diagnostic_evaluation_runs": (
            "fk_diagnostic_evaluation_runs_company_same_tenant",
            "fk_diagnostic_evaluation_runs_branch_same_tenant",
        ),
        "diagnostic_findings": (
            "fk_diagnostic_findings_company_same_tenant",
            "fk_diagnostic_findings_branch_same_tenant",
        ),
        "diagnostic_suppressions": (
            "fk_diagnostic_suppressions_company_same_tenant",
            "fk_diagnostic_suppressions_branch_same_tenant",
        ),
        "diagnostic_incidents": (
            "fk_diagnostic_incidents_company_same_tenant",
            "fk_diagnostic_incidents_branch_same_tenant",
        ),
    }

    for table_name, (company_name, branch_name) in expected_by_table.items():
        foreign_keys = _named_foreign_keys(_table(table_name))
        assert tuple(column.name for column in foreign_keys[company_name].columns) == (
            "tenant_id",
            "company_id",
        )
        assert tuple(column.name for column in foreign_keys[branch_name].columns) == (
            "tenant_id",
            "company_id",
            "branch_id",
        )
        assert foreign_keys[company_name].ondelete == "RESTRICT"
        assert foreign_keys[branch_name].ondelete == "RESTRICT"


def test_scope_checks_cover_tenant_company_and_branch() -> None:
    for table_name in (
        "diagnostic_evaluation_runs",
        "diagnostic_findings",
        "diagnostic_suppressions",
        "diagnostic_incidents",
    ):
        checks = _named_checks(_table(table_name))
        scope_check = checks[f"ck_{table_name}_scope"]
        scope_type_check = checks[f"ck_{table_name}_scope_type"]
        for scope_type in RULE_SCOPE_TYPES:
            assert repr(scope_type) in scope_type_check
        assert "scope_type = 'tenant' AND company_id IS NULL AND branch_id IS NULL" in scope_check
        assert (
            "scope_type = 'company' AND company_id IS NOT NULL AND branch_id IS NULL" in scope_check
        )
        assert (
            "scope_type = 'branch' AND company_id IS NOT NULL AND branch_id IS NOT NULL"
            in scope_check
        )


def test_evaluation_runs_have_tenant_safe_idempotency_and_sanitized_errors() -> None:
    table = _table("diagnostic_evaluation_runs")
    checks = _named_checks(table)

    unique_columns = _unique_columns(table)
    assert ("tenant_id", "idempotency_key") in unique_columns
    assert ("tenant_id", "id", "scope_type") in unique_columns
    assert ("tenant_id", "id", "company_id") in unique_columns
    assert ("tenant_id", "id", "branch_id") in unique_columns
    assert {"error_type", "error_code", "error_message"} <= set(table.c.keys())
    assert "stack_trace" not in table.c
    assert "payload" not in table.c
    for value in EVALUATION_TRIGGER_TYPES:
        assert repr(value) in checks["ck_diagnostic_evaluation_runs_trigger_type"]
    for value in EVALUATION_STATUSES:
        assert repr(value) in checks["ck_diagnostic_evaluation_runs_status"]
    for value in EVALUATION_ERROR_TYPES:
        assert repr(value) in checks["ck_diagnostic_evaluation_runs_error_type"]
    assert "rules_evaluated >= 0" in checks["ck_diagnostic_evaluation_runs_counters"]


def test_findings_reference_run_and_exact_rule_version_without_cross_tenant_rules() -> None:
    foreign_keys = _foreign_key_signatures(_table("diagnostic_findings"))

    assert (
        ("tenant_id", "evaluation_run_id", "scope_type"),
        (
            "diagnostic_evaluation_runs.tenant_id",
            "diagnostic_evaluation_runs.id",
            "diagnostic_evaluation_runs.scope_type",
        ),
    ) in foreign_keys
    assert (
        ("tenant_id", "evaluation_run_id", "company_id"),
        (
            "diagnostic_evaluation_runs.tenant_id",
            "diagnostic_evaluation_runs.id",
            "diagnostic_evaluation_runs.company_id",
        ),
    ) in foreign_keys
    assert (
        ("tenant_id", "evaluation_run_id", "branch_id"),
        (
            "diagnostic_evaluation_runs.tenant_id",
            "diagnostic_evaluation_runs.id",
            "diagnostic_evaluation_runs.branch_id",
        ),
    ) in foreign_keys
    assert (
        ("rule_definition_id", "rule_version_number"),
        (
            "diagnostic_rule_versions.rule_definition_id",
            "diagnostic_rule_versions.version_number",
        ),
    ) in foreign_keys
    assert (
        ("rule_tenant_id", "rule_definition_id", "rule_ownership_type"),
        (
            "diagnostic_rule_definitions.tenant_id",
            "diagnostic_rule_definitions.id",
            "diagnostic_rule_definitions.ownership_type",
        ),
    ) in foreign_keys
    ownership_check = _named_checks(_table("diagnostic_findings"))[
        "ck_diagnostic_findings_rule_ownership"
    ]
    assert "rule_tenant_id = tenant_id" in ownership_check


def test_evidences_are_factual_versioned_and_same_tenant() -> None:
    table = _table("diagnostic_evidences")
    checks = _named_checks(table)

    assert (
        ("tenant_id", "diagnostic_id"),
        ("diagnostic_findings.tenant_id", "diagnostic_findings.id"),
    ) in _foreign_key_signatures(table)
    for value in EVIDENCE_TYPES:
        assert repr(value) in checks["ck_diagnostic_evidences_type"]
    for value in EVIDENCE_DIRECTIONS:
        assert repr(value) in checks["ck_diagnostic_evidences_direction"]
    for value in EVIDENCE_SOURCES:
        assert repr(value) in checks["ck_diagnostic_evidences_source"]
    assert {"analytics_data_version", "formula_version", "evidence_hash", "stable_order"} <= set(
        table.c.keys()
    )


def test_hypotheses_distinguish_assessment_states_and_link_supporting_evidence() -> None:
    hypothesis_checks = _named_checks(_table("diagnostic_hypotheses"))
    link_checks = _named_checks(_table("diagnostic_hypothesis_evidences"))

    for value in HYPOTHESIS_STATUSES:
        assert repr(value) in hypothesis_checks["ck_diagnostic_hypotheses_status"]
    for value in HYPOTHESIS_EVIDENCE_RELATIONS:
        assert repr(value) in link_checks["ck_diagnostic_hypothesis_evidences_relation"]
    hypothesis_table = _table("diagnostic_hypotheses")
    evidence_table = _table("diagnostic_evidences")
    link_table = _table("diagnostic_hypothesis_evidences")
    assert ("tenant_id", "diagnostic_id", "id") in _unique_columns(hypothesis_table)
    assert ("tenant_id", "diagnostic_id", "id") in _unique_columns(evidence_table)
    assert "diagnostic_id" in link_table.c
    link_foreign_keys = _foreign_key_signatures(link_table)
    hypothesis_fk = (
        ("tenant_id", "diagnostic_id", "hypothesis_id"),
        (
            "diagnostic_hypotheses.tenant_id",
            "diagnostic_hypotheses.diagnostic_id",
            "diagnostic_hypotheses.id",
        ),
    )
    evidence_fk = (
        ("tenant_id", "diagnostic_id", "evidence_id"),
        (
            "diagnostic_evidences.tenant_id",
            "diagnostic_evidences.diagnostic_id",
            "diagnostic_evidences.id",
        ),
    )
    assert hypothesis_fk in link_foreign_keys
    assert evidence_fk in link_foreign_keys
    assert all(
        "diagnostic_id" in local_columns
        for local_columns, target_columns in link_foreign_keys
        if target_columns[0].startswith("diagnostic_hypotheses.")
        or target_columns[0].startswith("diagnostic_evidences.")
    )
    assert (
        ("tenant_id", "hypothesis_id"),
        ("diagnostic_hypotheses.tenant_id", "diagnostic_hypotheses.id"),
    ) not in link_foreign_keys
    assert (
        ("tenant_id", "evidence_id"),
        ("diagnostic_evidences.tenant_id", "diagnostic_evidences.id"),
    ) not in link_foreign_keys


def test_action_recommendations_reference_exact_catalog_entry_and_require_human_review() -> None:
    table = _table("diagnostic_action_recommendations")
    checks = _named_checks(table)

    assert (
        ("catalog_entry_id",),
        ("diagnostic_action_catalog_entries.id",),
    ) in _foreign_key_signatures(table)
    assert checks["ck_diagnostic_action_recommendations_human_review"] == (
        "requires_human_review = true"
    )
    for value in ACTION_RECOMMENDATION_STATUSES:
        assert repr(value) in checks["ck_diagnostic_action_recommendations_status"]
    assert "allows_automatic_financial_execution" not in table.c
    assert "approved_for_execution" not in table.c


def test_suppressions_distinguish_cooldown_manual_and_rule_exception() -> None:
    table = _table("diagnostic_suppressions")
    checks = _named_checks(table)

    for value in SUPPRESSION_TYPES:
        assert repr(value) in checks["ck_diagnostic_suppressions_type"]
    for value in SUPPRESSION_TARGET_TYPES:
        assert repr(value) in checks["ck_diagnostic_suppressions_target_type"]
    for value in SUPPRESSION_REASONS:
        assert repr(value) in checks["ck_diagnostic_suppressions_reason"]
    for value in SUPPRESSION_SOURCES:
        assert repr(value) in checks["ck_diagnostic_suppressions_source"]
    for value in SUPPRESSION_STATUSES:
        assert repr(value) in checks["ck_diagnostic_suppressions_status"]
    type_source = checks["ck_diagnostic_suppressions_type_source"]
    assert "suppression_type = 'cooldown' AND source = 'engine'" in type_source
    assert "suppression_type = 'manual' AND source = 'user'" in type_source
    assert "suppression_type = 'rule_exception' AND source = 'configuration'" in type_source
    assert "ends_at > starts_at" in checks["ck_diagnostic_suppressions_period"]
    assert "expires_at >= starts_at" in checks["ck_diagnostic_suppressions_expiration"]


def test_incidents_and_memberships_cannot_cross_tenants() -> None:
    incident_foreign_keys = _foreign_key_signatures(_table("diagnostic_incidents"))
    membership_foreign_keys = _foreign_key_signatures(_table("diagnostic_incident_memberships"))

    assert (
        ("tenant_id", "primary_diagnostic_id"),
        ("diagnostic_findings.tenant_id", "diagnostic_findings.id"),
    ) in incident_foreign_keys
    assert (
        ("tenant_id", "incident_id"),
        ("diagnostic_incidents.tenant_id", "diagnostic_incidents.id"),
    ) in membership_foreign_keys
    assert (
        ("tenant_id", "diagnostic_id"),
        ("diagnostic_findings.tenant_id", "diagnostic_findings.id"),
    ) in membership_foreign_keys


def test_hashes_fingerprints_statuses_severities_and_priorities_are_closed() -> None:
    finding_checks = _named_checks(_table("diagnostic_findings"))
    evidence_checks = _named_checks(_table("diagnostic_evidences"))
    incident_checks = _named_checks(_table("diagnostic_incidents"))

    assert "^[0-9a-f]{64}$" in finding_checks["ck_diagnostic_findings_fingerprint"]
    assert "^[0-9a-f]{64}$" in evidence_checks["ck_diagnostic_evidences_hash"]
    assert "^[0-9a-f]{64}$" in incident_checks["ck_diagnostic_incidents_fingerprint"]
    for value in DIAGNOSTIC_STATUSES:
        assert repr(value) in finding_checks["ck_diagnostic_findings_status"]
    for value in INCIDENT_STATUSES:
        assert repr(value) in incident_checks["ck_diagnostic_incidents_status"]
    for value in SEVERITIES:
        assert repr(value) in finding_checks["ck_diagnostic_findings_severity"]
        assert repr(value) in incident_checks["ck_diagnostic_incidents_severity"]
    for priority in ACTION_PRIORITIES:
        assert str(priority) in finding_checks["ck_diagnostic_findings_priority"]
        assert str(priority) in incident_checks["ck_diagnostic_incidents_priority"]
    for value in ACTION_DOMAINS:
        assert repr(value) in finding_checks["ck_diagnostic_findings_domain"]
        assert repr(value) in incident_checks["ck_diagnostic_incidents_domain"]


def test_relational_fields_are_not_hidden_in_jsonb() -> None:
    expected_relational = {
        "diagnostic_evaluation_runs": {
            "tenant_id",
            "scope_type",
            "trigger_type",
            "status",
            "engine_version",
            "analytics_data_version",
            "idempotency_key",
        },
        "diagnostic_findings": {
            "evaluation_run_id",
            "rule_definition_id",
            "rule_version_number",
            "fingerprint",
            "domain",
            "severity",
            "priority",
            "status",
            "primary_kpi_code",
            "analytics_data_version",
            "formula_version",
        },
        "diagnostic_evidences": {
            "diagnostic_id",
            "evidence_type",
            "kpi_code",
            "direction",
            "source_type",
            "evidence_hash",
            "stable_order",
        },
        "diagnostic_hypotheses": {
            "diagnostic_id",
            "hypothesis_code",
            "evaluation_status",
            "confidence_score",
            "rank",
            "logic_version",
        },
        "diagnostic_hypothesis_evidences": {
            "diagnostic_id",
            "hypothesis_id",
            "evidence_id",
            "relation",
            "stable_order",
        },
        "diagnostic_action_recommendations": {
            "diagnostic_id",
            "catalog_entry_id",
            "suggested_priority",
            "stable_order",
            "status",
            "requires_human_review",
        },
        "diagnostic_suppressions": {
            "scope_type",
            "suppression_type",
            "target_type",
            "reason_code",
            "source",
            "status",
            "starts_at",
            "ends_at",
            "expires_at",
        },
        "diagnostic_incidents": {
            "incident_code",
            "fingerprint",
            "domain",
            "aggregate_severity",
            "priority",
            "status",
            "diagnostic_count",
            "primary_diagnostic_id",
        },
    }

    for table_name, columns in expected_relational.items():
        assert columns <= set(_table(table_name).c.keys())


def test_jsonb_is_limited_to_controlled_snapshots() -> None:
    jsonb_columns = {
        table_name: {
            column.name for column in _table(table_name).columns if isinstance(column.type, JSONB)
        }
        for table_name in OPERATIONAL_TABLE_NAMES
    }

    assert jsonb_columns == {
        "diagnostic_evaluation_runs": set(),
        "diagnostic_findings": {"context_snapshot"},
        "diagnostic_evidences": {"detail_snapshot"},
        "diagnostic_hypotheses": {"definition_snapshot"},
        "diagnostic_hypothesis_evidences": set(),
        "diagnostic_action_recommendations": set(),
        "diagnostic_suppressions": set(),
        "diagnostic_incidents": set(),
        "diagnostic_incident_memberships": set(),
    }


def test_retention_ondelete_choices_preserve_operational_history() -> None:
    finding_fks = _named_foreign_keys(_table("diagnostic_findings"))
    evidence_fks = _named_foreign_keys(_table("diagnostic_evidences"))
    recommendation_fks = _named_foreign_keys(_table("diagnostic_action_recommendations"))
    membership_fks = _named_foreign_keys(_table("diagnostic_incident_memberships"))

    assert finding_fks["fk_diagnostic_findings_run_same_scope"].ondelete == "RESTRICT"
    assert finding_fks["fk_diagnostic_findings_run_same_company"].ondelete == "RESTRICT"
    assert finding_fks["fk_diagnostic_findings_run_same_branch"].ondelete == "RESTRICT"
    assert finding_fks["fk_diagnostic_findings_rule_version"].ondelete == "RESTRICT"
    assert evidence_fks["fk_diagnostic_evidences_finding_same_tenant"].ondelete == "RESTRICT"
    assert (
        recommendation_fks["fk_diagnostic_action_recommendations_finding_same_tenant"].ondelete
        == "RESTRICT"
    )
    assert (
        membership_fks["fk_diagnostic_incident_memberships_incident_same_tenant"].ondelete
        == "CASCADE"
    )
    assert (
        membership_fks["fk_diagnostic_incident_memberships_finding_same_tenant"].ondelete
        == "RESTRICT"
    )


def test_postgresql_ddl_compiles_for_all_operational_tables_and_indexes() -> None:
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]

    for table_name in sorted(OPERATIONAL_TABLE_NAMES):
        table = _table(table_name)
        create_table_sql = str(CreateTable(table).compile(dialect=dialect))
        assert f"CREATE TABLE {table_name}" in create_table_sql
        for index in sorted(table.indexes, key=lambda item: item.name or ""):
            assert str(CreateIndex(index).compile(dialect=dialect))


def test_operational_models_do_not_depend_on_future_migration_or_runtime_layers() -> None:
    source = _source(diagnostics_models)

    assert "20260719_0005" not in source
    assert "alembic" not in source
    assert "pharma_api.api" not in source
    assert "pharma_api.application" not in source
    assert "pharma_worker" not in source
    assert "redis" not in source.lower()
    assert "frontend" not in source.lower()


def test_future_diagnostics_migration_was_not_created() -> None:
    migration_dir = Path(__file__).parents[1] / "alembic" / "versions"

    assert not list(migration_dir.glob("20260719_0005*"))
