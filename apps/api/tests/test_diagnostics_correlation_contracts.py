from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast

import pytest

from pharma_api.domain.diagnostics.correlation_contracts import (
    CORRELATION_ALGORITHM_VERSION,
    CORRELATION_CONTRACT_VERSION,
    MAX_CLUSTER_MEMBERS,
    MAX_CORRELATION_POLICIES,
    CorrelationPolicyDefinition,
    CorrelationValidationError,
)
from pharma_api.domain.diagnostics.correlation_policies import (
    CORRELATION_MANIFEST,
    CORRELATION_MANIFEST_HASH,
    CORRELATION_POLICY_BY_CODE,
    CORRELATION_POLICY_CATALOG,
    CORRELATION_POLICY_CATALOG_HASH,
    validate_correlation_policy_catalog,
)
from pharma_api.domain.diagnostics.rules.catalog import RULE_CATALOG, RULE_CATALOG_HASH
from pharma_api.domain.diagnostics.rules.inventory import INVENTORY_RULES
from pharma_api.domain.diagnostics.rules.margin import MARGIN_RULES
from pharma_api.domain.diagnostics.rules.operations import OPERATIONS_RULES
from pharma_api.domain.diagnostics.rules.purchases import PURCHASES_RULES
from pharma_api.domain.diagnostics.rules.sales import SALES_RULES
from pharma_api.domain.diagnostics.rules.suppliers import SUPPLIERS_RULES
from pharma_api.domain.diagnostics.rules.validation import catalog_hash

EXPECTED_POLICY_CATALOG_HASH = "e03ec1f087c0abecf525b50fe6c28a619c1bf7573d1045c62cfe5d67355488f8"
EXPECTED_MANIFEST_HASH = "fa032f163789a6173f106e938d80d049c8c4e0aea059ad9535839948c1f95e31"
EXPECTED_RULE_HASHES = {
    "inventory": "8417fe46225afc3990f2af0a0d4c95d8c8ac7b78294c40b48b3f349d0a4e52f7",
    "sales": "b6bf16a32887f201481dfa085a2078afb9510aa42e39c1777ec532ce36eeb110",
    "margin": "c9e4a8fcd033e05e3f40dbe23f376d7c616e1fd93b7ff1f95cf113eb183b6a6a",
    "purchases": "2b6579d1cc6f589cec8901b5b31dba2d57638ba14a55d09bfb4dc6c312f0d995",
    "suppliers": "d7b93b6e0a8fefdf14daaaf1de493460dd28c8295b13231f5b634f19d40fc070",
    "operations": "b601c913c8794b3e3d9d19b928b526034d6a949d33fb9f1a30068f8d605960ee",
    "global": "560d09afde801699b15eae70462ae101c587d95f4d583b40a4128ab72c2424bb",
}


def test_policy_catalog_has_thirty_eight_explicit_ordered_policies() -> None:
    assert len(CORRELATION_POLICY_CATALOG) == 38
    assert len(CORRELATION_POLICY_CATALOG) <= MAX_CORRELATION_POLICIES
    assert [policy.code for policy in CORRELATION_POLICY_CATALOG] == sorted(
        policy.code for policy in CORRELATION_POLICY_CATALOG
    )
    assert len({policy.code for policy in CORRELATION_POLICY_CATALOG}) == 38
    assert len({policy.policy_hash for policy in CORRELATION_POLICY_CATALOG}) == 38


def test_policy_catalog_hash_and_manifest_hash_are_golden() -> None:
    assert CORRELATION_POLICY_CATALOG_HASH == EXPECTED_POLICY_CATALOG_HASH
    assert CORRELATION_MANIFEST_HASH == EXPECTED_MANIFEST_HASH
    assert CORRELATION_MANIFEST.contract_version == CORRELATION_CONTRACT_VERSION
    assert CORRELATION_MANIFEST.algorithm_version == CORRELATION_ALGORITHM_VERSION
    assert CORRELATION_MANIFEST.policy_count == 38


def test_policy_catalog_is_deeply_immutable() -> None:
    policy = CORRELATION_POLICY_CATALOG[0]
    with pytest.raises(FrozenInstanceError):
        policy.version = 2  # type: ignore[misc]
    with pytest.raises(TypeError):
        CORRELATION_POLICY_BY_CODE[policy.code] = policy  # type: ignore[index]
    assert isinstance(policy.member_diagnostic_codes, tuple)
    assert isinstance(policy.limitations, tuple)


def test_every_policy_is_same_domain_same_kpi_and_exact_scope_period() -> None:
    for policy in CORRELATION_POLICY_CATALOG:
        assert len(policy.domains) == 1
        assert len(policy.compatible_kpi_codes) == 1
        assert policy.scope_compatibility == "exact"
        assert policy.temporal_compatibility == "same_affected_period"
        assert policy.primary_selection_rule == ("severity_priority_confidence_recency_lexical")
        assert policy.severity_aggregation_rule == "maximum"
        assert policy.priority_aggregation_rule == "minimum"
        assert 2 <= len(policy.member_diagnostic_codes) <= MAX_CLUSTER_MEMBERS


def test_inventory_coverage_opposites_are_deliberately_not_correlated() -> None:
    policy_members = {
        code for policy in CORRELATION_POLICY_CATALOG for code in policy.member_diagnostic_codes
    }
    assert "inventory.high_coverage" not in policy_members
    assert "inventory.low_coverage" not in policy_members
    assert "inventory.slow_moving_coverage" not in policy_members


def test_catalog_validator_rejects_duplicate_membership() -> None:
    first = CORRELATION_POLICY_CATALOG[0]
    second = CorrelationPolicyDefinition(
        code="correlation.duplicate_membership_probe",
        version=1,
        domains=first.domains,
        member_diagnostic_codes=first.member_diagnostic_codes,
        compatible_kpi_codes=first.compatible_kpi_codes,
        scope_compatibility="exact",
        temporal_compatibility="same_affected_period",
        reason="Validate deterministic rejection of overlapping policy membership.",
        primary_selection_rule="severity_priority_confidence_recency_lexical",
        severity_aggregation_rule="maximum",
        priority_aggregation_rule="minimum",
        limitations=("Test-only invalid overlapping policy.",),
    )
    with pytest.raises(CorrelationValidationError, match="multiple correlation policies"):
        validate_correlation_policy_catalog(
            tuple(sorted((first, second), key=lambda item: item.code))
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("scope_compatibility", "fuzzy", "scope compatibility"),
        ("temporal_compatibility", "overlap", "temporal compatibility"),
        ("status", "inactive", "status"),
    ),
)
def test_policy_contract_rejects_unsupported_runtime_literals(
    field: str,
    value: str,
    message: str,
) -> None:
    source = CORRELATION_POLICY_CATALOG[0]
    payload = {
        "code": "correlation.invalid_runtime_literal",
        "version": 1,
        "domains": source.domains,
        "member_diagnostic_codes": source.member_diagnostic_codes,
        "compatible_kpi_codes": source.compatible_kpi_codes,
        "scope_compatibility": source.scope_compatibility,
        "temporal_compatibility": source.temporal_compatibility,
        "reason": "Reject unsupported policy runtime literals deterministically.",
        "primary_selection_rule": source.primary_selection_rule,
        "severity_aggregation_rule": source.severity_aggregation_rule,
        "priority_aggregation_rule": source.priority_aggregation_rule,
        "limitations": ("Test-only invalid policy literal.",),
        "status": source.status,
    }
    payload[field] = value
    with pytest.raises(CorrelationValidationError, match=message):
        CorrelationPolicyDefinition(**cast(Any, payload))


def test_policy_member_limit_is_enforced_before_processing() -> None:
    members = tuple(f"sales.synthetic_{index}" for index in range(MAX_CLUSTER_MEMBERS + 1))
    with pytest.raises(CorrelationValidationError, match=r"2\.\.MAX_CLUSTER_MEMBERS"):
        CorrelationPolicyDefinition(
            code="correlation.synthetic_limit",
            version=1,
            domains=("sales",),
            member_diagnostic_codes=members,
            compatible_kpi_codes=("sales.net_revenue",),
            scope_compatibility="exact",
            temporal_compatibility="same_affected_period",
            reason="Bound policy cardinality before any correlation work begins.",
            primary_selection_rule="severity_priority_confidence_recency_lexical",
            severity_aggregation_rule="maximum",
            priority_aggregation_rule="minimum",
            limitations=("Synthetic invalid policy for a limit regression.",),
        )


def test_policy_serialization_is_canonical_and_repeatable() -> None:
    first = json.dumps(
        [policy.as_dict() for policy in CORRELATION_POLICY_CATALOG],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    second = json.dumps(
        [policy.as_dict() for policy in CORRELATION_POLICY_CATALOG],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    assert first == second


def test_all_120_rule_hashes_are_preserved_exactly() -> None:
    assert len(RULE_CATALOG) == 120
    assert catalog_hash(INVENTORY_RULES) == EXPECTED_RULE_HASHES["inventory"]
    assert catalog_hash(SALES_RULES) == EXPECTED_RULE_HASHES["sales"]
    assert catalog_hash(MARGIN_RULES) == EXPECTED_RULE_HASHES["margin"]
    assert catalog_hash(PURCHASES_RULES) == EXPECTED_RULE_HASHES["purchases"]
    assert catalog_hash(SUPPLIERS_RULES) == EXPECTED_RULE_HASHES["suppliers"]
    assert catalog_hash(OPERATIONS_RULES) == EXPECTED_RULE_HASHES["operations"]
    assert EXPECTED_RULE_HASHES["global"] == RULE_CATALOG_HASH


def test_correlation_modules_do_not_import_infrastructure_or_disallowed_sources() -> None:
    root = Path(__file__).parents[1] / "src" / "pharma_api" / "domain" / "diagnostics"
    paths = (
        root / "correlation_contracts.py",
        root / "correlation_policies.py",
        root / "correlation.py",
    )
    forbidden_calls = {"hash", "uuid4", "random", "secrets", "time", "now"}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = [alias.name for alias in node.names]
                if isinstance(node, ast.ImportFrom) and node.module is not None:
                    modules.append(node.module)
                assert not any("infrastructure" in module for module in modules)
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id not in forbidden_calls
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in forbidden_calls


def test_algorithm_source_has_indexing_and_no_unrestricted_pairwise_helpers() -> None:
    path = (
        Path(__file__).parents[1]
        / "src"
        / "pharma_api"
        / "domain"
        / "diagnostics"
        / "correlation.py"
    )
    source = path.read_text(encoding="utf-8")
    assert "O(n log n + p log p)" in source
    assert "by_code" in source
    assert "grouped" in source
    assert "itertools.combinations" not in source
    assert "itertools.product" not in source
