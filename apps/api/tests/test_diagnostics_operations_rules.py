from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Literal
from uuid import UUID

import pytest

from pharma_api.domain.analytics.kpis import KPI_BY_CODE, UNAVAILABLE_KPIS
from pharma_api.domain.diagnostics.actions import ACTION_BY_CODE
from pharma_api.domain.diagnostics.conditions import (
    AbsChange,
    AllOf,
    Compare,
    Condition,
    Fixed,
    PctChange,
    Persisted,
)
from pharma_api.domain.diagnostics.engine import (
    EvaluationScope,
    KPIObservation,
    ObservationFrame,
    RuleEvaluationInput,
    evaluate_rule,
)
from pharma_api.domain.diagnostics.rules import (
    RULE_BY_CODE,
    RULE_CATALOG,
    RULE_CATALOG_HASH,
    RULE_CATALOG_MANIFEST,
)
from pharma_api.domain.diagnostics.rules.inventory import INVENTORY_RULES
from pharma_api.domain.diagnostics.rules.margin import MARGIN_RULES
from pharma_api.domain.diagnostics.rules.operations import OPERATIONS_RULES
from pharma_api.domain.diagnostics.rules.purchases import PURCHASES_RULES
from pharma_api.domain.diagnostics.rules.sales import SALES_RULES
from pharma_api.domain.diagnostics.rules.suppliers import SUPPLIERS_RULES
from pharma_api.domain.diagnostics.rules.validation import (
    catalog_hash,
    catalog_manifest,
    validate_catalog,
    validate_rule,
)

TENANT_ID = UUID("10000000-0000-0000-0000-000000000601")
COMPANY_ID = UUID("20000000-0000-0000-0000-000000000601")
BRANCH_ID = UUID("30000000-0000-0000-0000-000000000601")
WINDOW_START = datetime(2026, 7, 15, tzinfo=UTC)
WINDOW_END = datetime(2026, 7, 21, 23, 59, 59, tzinfo=UTC)
EVALUATED_AT = datetime(2026, 7, 22, 8, tzinfo=UTC)
EXPECTED_INVENTORY_HASH = "8417fe46225afc3990f2af0a0d4c95d8c8ac7b78294c40b48b3f349d0a4e52f7"
EXPECTED_SALES_HASH = "b6bf16a32887f201481dfa085a2078afb9510aa42e39c1777ec532ce36eeb110"
EXPECTED_MARGIN_HASH = "c9e4a8fcd033e05e3f40dbe23f376d7c616e1fd93b7ff1f95cf113eb183b6a6a"
EXPECTED_PURCHASES_HASH = "2b6579d1cc6f589cec8901b5b31dba2d57638ba14a55d09bfb4dc6c312f0d995"
EXPECTED_SUPPLIERS_HASH = "d7b93b6e0a8fefdf14daaaf1de493460dd28c8295b13231f5b634f19d40fc070"
EXPECTED_OPERATIONS_HASH = "b601c913c8794b3e3d9d19b928b526034d6a949d33fb9f1a30068f8d605960ee"
EXPECTED_GLOBAL_HASH = "560d09afde801699b15eae70462ae101c587d95f4d583b40a4128ab72c2424bb"

ObservationKind = Literal[
    "current",
    "goal",
    "previous",
    "year_ago",
    "network_average",
    "category_average",
    "moving_average",
    "trend",
    "frequency",
    "concentration",
    "percentile",
]
DirectionalOperator = Literal["lt", "gt"]
EvaluationState = Literal["matched", "not_matched"]

DIRECTIONAL_CHANGE_RULES: tuple[tuple[str, DirectionalOperator], ...] = (
    ("operations.completeness_decline", "lt"),
    ("operations.consistency_decline", "lt"),
    ("operations.data_freshness_increase", "gt"),
    ("operations.duplicate_rate_increase", "gt"),
    ("operations.failed_batches_increase", "gt"),
    ("operations.ingestion_duration_increase", "gt"),
    ("operations.integration_availability_decline", "lt"),
    ("operations.rejection_rate_increase", "gt"),
    ("operations.source_lag_increase", "gt"),
)


@dataclass(frozen=True, slots=True)
class GoldenCase:
    rule_code: str
    matched_value: str
    unmatched_value: str
    reference_kind: ObservationKind | None = None
    reference_value: str | None = None
    persisted: bool = False


CASES = (
    GoldenCase("operations.completeness_below_network", "8", "12", "network_average", "10"),
    GoldenCase("operations.completeness_decline", "8", "12", "previous", "10"),
    GoldenCase("operations.consistency_below_network", "8", "12", "network_average", "10"),
    GoldenCase("operations.consistency_decline", "8", "12", "previous", "10"),
    GoldenCase("operations.data_freshness_above_network", "12", "8", "network_average", "10"),
    GoldenCase("operations.data_freshness_increase", "12", "8", "previous", "10"),
    GoldenCase("operations.duplicate_rate_above_network", "12", "8", "network_average", "10"),
    GoldenCase("operations.duplicate_rate_increase", "12", "8", "previous", "10"),
    GoldenCase("operations.duplicate_rate_positive", "1", "0"),
    GoldenCase("operations.failed_batches_increase", "12", "8", "previous", "10"),
    GoldenCase("operations.failed_batches_persistent_positive", "1", "0", persisted=True),
    GoldenCase("operations.failed_batches_positive", "1", "0"),
    GoldenCase("operations.ingestion_duration_increase", "12", "8", "previous", "10"),
    GoldenCase("operations.integration_availability_decline", "8", "12", "previous", "10"),
    GoldenCase("operations.integration_availability_zero", "0", "1"),
    GoldenCase("operations.quality_incidents_positive", "1", "0"),
    GoldenCase("operations.rejection_rate_above_network", "12", "8", "network_average", "10"),
    GoldenCase("operations.rejection_rate_increase", "12", "8", "previous", "10"),
    GoldenCase("operations.rejection_rate_positive", "1", "0"),
    GoldenCase("operations.source_lag_increase", "12", "8", "previous", "10"),
)


def _observation(
    kpi_code: str,
    value: str | None,
    *,
    kind: ObservationKind = "current",
    period_start: datetime = WINDOW_START,
    period_end: datetime = WINDOW_END,
) -> KPIObservation:
    return KPIObservation(
        kpi_code=kpi_code,
        value=None if value is None else Decimal(value),
        kind=kind,
        quality_score=Decimal("1"),
        coverage=Decimal("1"),
        data_version=26,
        formula_version=1,
        lineage_ref=f"lineage://operations/{kpi_code.replace('.', '/')}/{kind}",
        period_start=period_start,
        period_end=period_end,
    )


def _positive_history(kpi_code: str) -> tuple[ObservationFrame, ...]:
    frames: list[ObservationFrame] = []
    for index in range(2):
        start = WINDOW_START - timedelta(days=14 - 7 * index)
        end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
        frames.append(
            ObservationFrame(
                (
                    _observation(
                        kpi_code,
                        "1",
                        period_start=start,
                        period_end=end,
                    ),
                )
            )
        )
    return tuple(frames)


def _evaluation(case: GoldenCase, *, matched: bool) -> RuleEvaluationInput:
    rule = RULE_BY_CODE[case.rule_code]
    selected = case.matched_value if matched else case.unmatched_value
    observations = [_observation(rule.primary_kpi_code, selected)]
    if case.reference_kind is not None:
        assert case.reference_value is not None
        observations.append(
            _observation(
                rule.primary_kpi_code,
                case.reference_value,
                kind=case.reference_kind,
            )
        )
    return RuleEvaluationInput(
        rule=rule.to_snapshot(),
        scope=EvaluationScope(
            tenant_id=TENANT_ID,
            scope_type="branch",
            company_id=COMPANY_ID,
            branch_id=BRANCH_ID,
        ),
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        analytics_data_version=26,
        observations=tuple(observations),
        history=_positive_history(rule.primary_kpi_code) if case.persisted else (),
        evaluated_at=EVALUATED_AT,
        engine_version="2d-cp2-b2f.1",
    )


def _evaluation_with_previous(
    rule_code: str,
    *,
    current: str,
    previous: str,
) -> RuleEvaluationInput:
    rule = RULE_BY_CODE[rule_code]
    return RuleEvaluationInput(
        rule=rule.to_snapshot(),
        scope=EvaluationScope(
            tenant_id=TENANT_ID,
            scope_type="branch",
            company_id=COMPANY_ID,
            branch_id=BRANCH_ID,
        ),
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        analytics_data_version=26,
        observations=(
            _observation(rule.primary_kpi_code, current),
            _observation(rule.primary_kpi_code, previous, kind="previous"),
        ),
        evaluated_at=EVALUATED_AT,
        engine_version="2d-cp2-b2f.1",
    )


def _comparison_nodes(condition: Condition) -> tuple[Compare, ...]:
    if isinstance(condition, Compare):
        return (condition,)
    if isinstance(condition, AllOf):
        return tuple(
            comparison for node in condition.nodes for comparison in _comparison_nodes(node)
        )
    if isinstance(condition, Persisted):
        return _comparison_nodes(condition.predicate)
    return ()


def _node_types(value: object) -> tuple[str, ...]:
    if isinstance(value, dict):
        found: list[str] = []
        node_type = value.get("type")
        if isinstance(node_type, str):
            found.append(node_type)
        for nested in value.values():
            found.extend(_node_types(nested))
        return tuple(found)
    if isinstance(value, list):
        return tuple(node_type for nested in value for node_type in _node_types(nested))
    return ()


def test_operations_catalog_has_twenty_real_ordered_unique_rules() -> None:
    assert len(OPERATIONS_RULES) == 20
    assert [rule.code for rule in OPERATIONS_RULES] == sorted(
        rule.code for rule in OPERATIONS_RULES
    )
    assert all(rule.domain == "operations" for rule in OPERATIONS_RULES)
    assert all(rule.status == "active" for rule in OPERATIONS_RULES)
    assert len({rule.code for rule in OPERATIONS_RULES}) == 20
    assert len({rule.rule_definition_id for rule in OPERATIONS_RULES}) == 20
    assert len({rule.to_snapshot().condition_hash for rule in OPERATIONS_RULES}) == 20
    assert len({rule.to_snapshot().definition_hash for rule in OPERATIONS_RULES}) == 20
    assert len({rule.governance_hash for rule in OPERATIONS_RULES}) == 20


def test_operations_rules_use_only_operational_kpis_and_exact_safe_actions() -> None:
    unavailable = {item.code for item in UNAVAILABLE_KPIS}
    for rule in OPERATIONS_RULES:
        validate_rule(rule)
        assert rule.primary_kpi_code in KPI_BY_CODE
        assert KPI_BY_CODE[rule.primary_kpi_code].category == "operations"
        assert set(rule.declared_kpi_codes).isdisjoint(unavailable)
        for reference in rule.actions:
            action = ACTION_BY_CODE[reference.action_code]
            assert action.domain == "operations"
            assert action.version == reference.action_version
            assert reference.suggested_priority == action.default_priority
            assert action.execution_mode == "human_review_required"
            assert action.allows_automatic_financial_execution is False


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.rule_code)
def test_operations_golden_cases_match_and_do_not_match(case: GoldenCase) -> None:
    matched = evaluate_rule(_evaluation(case, matched=True))
    unmatched = evaluate_rule(_evaluation(case, matched=False))

    assert matched.state == "matched"
    assert matched.issue is None
    assert matched.diagnostic is not None
    assert matched.evidence
    assert matched.hypotheses
    assert matched.recommendations
    assert unmatched.state == "not_matched"
    assert unmatched.issue is None
    assert unmatched.diagnostic is None
    assert unmatched.evidence == ()
    assert unmatched.recommendations == ()


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.rule_code)
def test_operations_evidence_is_factual_and_hypotheses_are_separate(case: GoldenCase) -> None:
    rule = RULE_BY_CODE[case.rule_code]
    result = evaluate_rule(_evaluation(case, matched=True))

    assert result.state == "matched"
    assert result.evidence[0].kpi_code in rule.declared_kpi_codes
    assert result.evidence[0].observed_value == Decimal(case.matched_value)
    assert all(
        item.evidence_code in {spec.evidence_code for spec in rule.evidence}
        for item in result.evidence
    )
    assert all(
        item.evaluation_status in {"supported", "contradicted", "inconclusive"}
        for item in result.hypotheses
    )
    for hypothesis in rule.hypotheses:
        text = hypothesis.explanation.casefold()
        assert "pode" in text or "podem" in text
        assert "foi causado por" not in text
        assert "comprova que" not in text


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.rule_code)
def test_operations_recommendations_remain_advisory_only(case: GoldenCase) -> None:
    result = evaluate_rule(_evaluation(case, matched=True))
    assert result.state == "matched"
    for recommendation in result.recommendations:
        assert recommendation.execution_mode == "human_review_required"
        assert recommendation.requires_human_review is True
        assert recommendation.allows_automatic_financial_execution is False


@pytest.mark.parametrize(
    "case",
    tuple(case for case in CASES if case.reference_kind is not None),
    ids=lambda case: case.rule_code,
)
def test_missing_governed_purchase_reference_is_skipped(case: GoldenCase) -> None:
    evaluation = _evaluation(case, matched=True)
    result = evaluate_rule(
        RuleEvaluationInput(
            rule=evaluation.rule,
            scope=evaluation.scope,
            window_start=evaluation.window_start,
            window_end=evaluation.window_end,
            analytics_data_version=evaluation.analytics_data_version,
            observations=(evaluation.observations[0],),
            history=evaluation.history,
            evaluated_at=evaluation.evaluated_at,
            engine_version=evaluation.engine_version,
        )
    )
    assert result.state == "skipped"
    assert result.issue is not None
    assert result.issue.code == "missing_kpi"
    assert result.diagnostic is None


def test_persistent_failed_batches_requires_two_history_frames() -> None:
    case = next(item for item in CASES if item.persisted)
    evaluation = _evaluation(case, matched=True)
    result = evaluate_rule(
        RuleEvaluationInput(
            rule=evaluation.rule,
            scope=evaluation.scope,
            window_start=evaluation.window_start,
            window_end=evaluation.window_end,
            analytics_data_version=evaluation.analytics_data_version,
            observations=evaluation.observations,
            history=evaluation.history[:1],
            evaluated_at=evaluation.evaluated_at,
            engine_version=evaluation.engine_version,
        )
    )
    assert result.state == "skipped"
    assert result.issue is not None
    assert result.issue.code == "condition_not_evaluable"


def test_persistent_failed_batches_does_not_match_after_current_recovery() -> None:
    case = next(item for item in CASES if item.persisted)
    result = evaluate_rule(_evaluation(case, matched=False))
    assert result.state == "not_matched"
    assert result.issue is None
    assert result.diagnostic is None
    assert result.evidence == ()
    assert result.recommendations == ()


@pytest.mark.parametrize(("rule_code", "operator"), DIRECTIONAL_CHANGE_RULES)
def test_directional_purchase_change_from_zero_is_evaluable(
    rule_code: str,
    operator: DirectionalOperator,
) -> None:
    current = "1" if operator == "gt" else "-1"
    result = evaluate_rule(_evaluation_with_previous(rule_code, current=current, previous="0"))
    assert result.state == "matched"
    assert result.issue is None


@pytest.mark.parametrize(("rule_code", "operator"), DIRECTIONAL_CHANGE_RULES)
@pytest.mark.parametrize(
    ("current", "direction"),
    (("-90", "increase"), ("-110", "decrease")),
)
def test_directional_purchase_change_has_no_negative_baseline_inversion(
    rule_code: str,
    operator: DirectionalOperator,
    current: str,
    direction: str,
) -> None:
    result = evaluate_rule(_evaluation_with_previous(rule_code, current=current, previous="-100"))
    expected: EvaluationState = (
        "matched"
        if (operator == "gt" and direction == "increase")
        or (operator == "lt" and direction == "decrease")
        else "not_matched"
    )
    assert result.state == expected
    assert result.issue is None


@pytest.mark.parametrize(("rule_code", "expected_operator"), DIRECTIONAL_CHANGE_RULES)
def test_directional_purchase_rules_use_absolute_change_ast(
    rule_code: str,
    expected_operator: DirectionalOperator,
) -> None:
    condition = RULE_BY_CODE[rule_code].condition
    comparisons = _comparison_nodes(condition)
    assert len(comparisons) == 1
    assert "abs_change" in _node_types(condition.as_json())
    assert "pct_change" not in _node_types(condition.as_json())
    comparison = comparisons[0]
    assert isinstance(comparison.left, AbsChange)
    assert not isinstance(comparison.left, PctChange)
    assert comparison.left.baseline == "previous"
    assert comparison.op == expected_operator
    assert isinstance(comparison.right, Fixed)
    assert comparison.right.value == Decimal("0")


def test_operations_manifest_is_deeply_immutable() -> None:
    first = catalog_manifest(OPERATIONS_RULES)[0]
    assert isinstance(first, MappingProxyType)
    assert isinstance(first["dimensions"], tuple)
    assert isinstance(first["actions"], tuple)
    actions = first["actions"]
    assert isinstance(actions[0], MappingProxyType)
    with pytest.raises(TypeError):
        first["code"] = "operations.changed"  # type: ignore[index]


def test_operations_slice_and_global_catalog_hashes_are_explicit_and_preserved() -> None:
    validate_catalog(RULE_CATALOG)
    assert catalog_hash(INVENTORY_RULES) == EXPECTED_INVENTORY_HASH
    assert catalog_hash(SALES_RULES) == EXPECTED_SALES_HASH
    assert catalog_hash(MARGIN_RULES) == EXPECTED_MARGIN_HASH
    assert catalog_hash(PURCHASES_RULES) == EXPECTED_PURCHASES_HASH
    assert catalog_hash(SUPPLIERS_RULES) == EXPECTED_SUPPLIERS_HASH
    assert catalog_hash(OPERATIONS_RULES) == EXPECTED_OPERATIONS_HASH
    assert RULE_CATALOG_HASH == EXPECTED_GLOBAL_HASH
    assert len(RULE_CATALOG) == 120
    assert len(RULE_CATALOG_MANIFEST) == 120


def test_operations_catalog_is_stable_across_python_hash_seeds() -> None:
    repository = Path(__file__).parents[3]
    source = """
import json
from pharma_api.domain.diagnostics.rules import RULE_CATALOG, RULE_CATALOG_HASH
from pharma_api.domain.diagnostics.rules.operations import OPERATIONS_RULES
from pharma_api.domain.diagnostics.rules.validation import catalog_hash
print(json.dumps({
    "global_hash": RULE_CATALOG_HASH,
    "slice_hash": catalog_hash(OPERATIONS_RULES),
    "codes": [rule.code for rule in RULE_CATALOG],
    "uuids": [str(rule.rule_definition_id) for rule in RULE_CATALOG],
    "conditions": [rule.to_snapshot().condition_hash for rule in RULE_CATALOG],
    "definitions": [rule.to_snapshot().definition_hash for rule in RULE_CATALOG],
    "governance": [rule.governance_hash for rule in RULE_CATALOG],
}, sort_keys=True))
"""
    outputs: list[str] = []
    for seed in ("1", "987654"):
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = seed
        environment["PYTHONPATH"] = str(repository / "apps" / "api" / "src")
        completed = subprocess.run(  # noqa: S603
            [sys.executable, "-c", source],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        outputs.append(completed.stdout.strip())
    assert outputs[0] == outputs[1]
    payload = json.loads(outputs[0])
    assert payload["slice_hash"] == EXPECTED_OPERATIONS_HASH
    assert payload["global_hash"] == EXPECTED_GLOBAL_HASH


def test_operations_rule_module_has_no_infrastructure_imports_or_pct_direction_test() -> None:
    path = (
        Path(__file__).parents[1]
        / "src"
        / "pharma_api"
        / "domain"
        / "diagnostics"
        / "rules"
        / "operations.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    assert not any("infrastructure" in imported for imported in imports)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "PctChange" not in imported_names
