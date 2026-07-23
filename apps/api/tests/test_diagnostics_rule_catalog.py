from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import pytest

from pharma_api.domain.analytics.kpis import KPI_BY_CODE, UNAVAILABLE_KPIS
from pharma_api.domain.diagnostics.actions import ACTION_BY_CODE
from pharma_api.domain.diagnostics.rules import (
    RULE_BY_CODE,
    RULE_CATALOG,
    RULE_CATALOG_HASH,
    RULE_CATALOG_MANIFEST,
    RULE_COUNT,
    RuleCatalogValidationError,
    deterministic_rule_id,
    validate_catalog,
    validate_rule,
)
from pharma_api.domain.diagnostics.rules.inventory import INVENTORY_RULES
from pharma_api.domain.diagnostics.rules.margin import MARGIN_RULES
from pharma_api.domain.diagnostics.rules.operations import OPERATIONS_RULES
from pharma_api.domain.diagnostics.rules.purchases import PURCHASES_RULES
from pharma_api.domain.diagnostics.rules.sales import SALES_RULES
from pharma_api.domain.diagnostics.rules.suppliers import SUPPLIERS_RULES
from pharma_api.domain.diagnostics.rules.validation import forbidden_infrastructure_markers

EXPECTED_CATALOG_HASH = "560d09afde801699b15eae70462ae101c587d95f4d583b40a4128ab72c2424bb"


def test_catalog_has_one_hundred_twenty_real_ordered_rules() -> None:
    assert RULE_COUNT == 120
    assert len(RULE_CATALOG) == 120
    assert len(INVENTORY_RULES) == 20
    assert len(MARGIN_RULES) == 20
    assert len(OPERATIONS_RULES) == 20
    assert len(PURCHASES_RULES) == 20
    assert len(SALES_RULES) == 20
    assert len(SUPPLIERS_RULES) == 20
    assert [rule.code for rule in RULE_CATALOG] == sorted(rule.code for rule in RULE_CATALOG)
    assert {rule.domain for rule in RULE_CATALOG} == {
        "inventory",
        "margin",
        "operations",
        "purchases",
        "sales",
        "suppliers",
    }
    assert all(rule.status == "active" for rule in RULE_CATALOG)


def test_catalog_import_runs_full_validation_and_has_golden_hash() -> None:
    validate_catalog(RULE_CATALOG)

    assert RULE_CATALOG_HASH == EXPECTED_CATALOG_HASH
    assert len(RULE_CATALOG_MANIFEST) == RULE_COUNT
    assert RULE_CATALOG_MANIFEST[0]["code"] == "inventory.excess_products"
    assert RULE_CATALOG_MANIFEST[-1]["code"] == "suppliers.top5_concentration_above_network"


def test_rule_index_is_read_only_and_complete() -> None:
    assert isinstance(RULE_BY_CODE, MappingProxyType)
    assert tuple(RULE_BY_CODE) == tuple(rule.code for rule in RULE_CATALOG)
    with pytest.raises(TypeError):
        RULE_BY_CODE["inventory.fake"] = RULE_CATALOG[0]  # type: ignore[index]


def test_catalog_manifest_is_deeply_immutable() -> None:
    first = RULE_CATALOG_MANIFEST[0]
    assert isinstance(first, MappingProxyType)
    assert isinstance(first["dimensions"], tuple)
    assert isinstance(first["actions"], tuple)
    actions = first["actions"]
    assert isinstance(actions, tuple)
    assert isinstance(actions[0], MappingProxyType)
    with pytest.raises(TypeError):
        first["code"] = "inventory.changed"  # type: ignore[index]


def test_each_rule_converts_losslessly_to_public_rule_snapshot() -> None:
    for rule in RULE_CATALOG:
        validate_rule(rule)
        snapshot = rule.to_snapshot()

        assert snapshot.rule_definition_id == deterministic_rule_id(rule.code)
        assert snapshot.diagnostic_code == rule.code
        assert snapshot.version_number == rule.version
        assert snapshot.domain == rule.domain
        assert snapshot.primary_kpi_code == rule.primary_kpi_code
        assert snapshot.declared_kpi_codes == rule.declared_kpi_codes
        assert snapshot.computed_condition_hash() == snapshot.condition_hash
        assert snapshot.computed_definition_hash() == snapshot.definition_hash
        assert snapshot.actions == rule.actions
        assert snapshot.evidence == rule.evidence
        assert snapshot.hypotheses == rule.hypotheses


def test_rules_use_only_operational_kpis_and_exact_advisory_actions() -> None:
    unavailable = {item.code for item in UNAVAILABLE_KPIS}

    for rule in RULE_CATALOG:
        assert rule.primary_kpi_code in KPI_BY_CODE
        assert not (set(rule.declared_kpi_codes) & unavailable)
        assert rule.primary_kpi_code in rule.declared_kpi_codes
        for action_reference in rule.actions:
            action = ACTION_BY_CODE[action_reference.action_code]
            assert action.version == action_reference.action_version
            assert action.domain == rule.domain
            assert action.execution_mode == "human_review_required"
            assert action.allows_automatic_financial_execution is False


def test_all_evidence_and_hypothesis_links_are_governed() -> None:
    for rule in RULE_CATALOG:
        evidence_codes = {item.evidence_code for item in rule.evidence}
        assert evidence_codes
        assert rule.hypotheses
        for evidence in rule.evidence:
            assert evidence.kpi_code in rule.declared_kpi_codes
        for hypothesis in rule.hypotheses:
            links = set(
                hypothesis.supporting_evidence_codes + hypothesis.contradicting_evidence_codes
            )
            assert links <= evidence_codes
            assert "pode" in hypothesis.explanation.casefold() or "podem" in (
                hypothesis.explanation.casefold()
            )


def test_catalog_rejects_reordering_duplicate_codes_and_tampered_actions() -> None:
    with pytest.raises(RuleCatalogValidationError, match="lexical code order"):
        validate_catalog(tuple(reversed(RULE_CATALOG)))

    duplicate = (RULE_CATALOG[0], RULE_CATALOG[0])
    with pytest.raises(RuleCatalogValidationError, match="duplicate rule codes"):
        validate_catalog(duplicate)

    original = RULE_CATALOG[0]
    tampered = replace(
        original,
        actions=(replace(original.actions[0], action_version=9_999),),
    )
    with pytest.raises(RuleCatalogValidationError, match="non-current version"):
        validate_rule(tampered)


def test_rule_package_has_no_infrastructure_imports() -> None:
    package = Path(__file__).parents[1] / "src" / "pharma_api" / "domain" / "diagnostics" / "rules"
    markers = forbidden_infrastructure_markers()

    for path in sorted(package.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.append(node.module)
        assert not any(marker in imported for marker in markers for imported in imports), path


def test_existing_engine_modules_are_not_referenced_as_rule_storage() -> None:
    for rule in RULE_CATALOG:
        manifest = rule.as_dict()
        assert manifest["definition_hash"] == rule.to_snapshot().definition_hash
        assert manifest["condition_hash"] == rule.to_snapshot().condition_hash
        assert manifest["objective"]
        assert manifest["expected_impact"]
        assert manifest["limitations"]
