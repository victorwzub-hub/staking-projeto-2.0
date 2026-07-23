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
from pharma_api.domain.diagnostics.rules.sales import SALES_RULES
from pharma_api.domain.diagnostics.rules.validation import (
    catalog_hash,
    catalog_manifest,
    validate_catalog,
    validate_rule,
)

TENANT_ID = UUID("10000000-0000-0000-0000-000000000301")
COMPANY_ID = UUID("20000000-0000-0000-0000-000000000301")
BRANCH_ID = UUID("30000000-0000-0000-0000-000000000301")
WINDOW_START = datetime(2026, 7, 15, tzinfo=UTC)
WINDOW_END = datetime(2026, 7, 21, 23, 59, 59, tzinfo=UTC)
EVALUATED_AT = datetime(2026, 7, 22, 8, tzinfo=UTC)
EXPECTED_INVENTORY_SLICE_HASH = "8417fe46225afc3990f2af0a0d4c95d8c8ac7b78294c40b48b3f349d0a4e52f7"
EXPECTED_SALES_SLICE_HASH = "b6bf16a32887f201481dfa085a2078afb9510aa42e39c1777ec532ce36eeb110"
EXPECTED_MARGIN_SLICE_HASH = "c9e4a8fcd033e05e3f40dbe23f376d7c616e1fd93b7ff1f95cf113eb183b6a6a"
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
    ("margin.discount_on_price_increase", "gt"),
    ("margin.gmroi_decline", "lt"),
    ("margin.gross_percent_decline", "lt"),
    ("margin.gross_profit_decline", "lt"),
    ("margin.negative_margin_rate_increase", "gt"),
    ("margin.profit_per_sale_decline", "lt"),
    ("margin.profit_per_unit_decline", "lt"),
)
NEGATIVE_BASELINE_DECLINE_RULES = (
    "margin.gmroi_decline",
    "margin.gross_percent_decline",
    "margin.gross_profit_decline",
    "margin.profit_per_sale_decline",
    "margin.profit_per_unit_decline",
)


@dataclass(frozen=True, slots=True)
class GoldenCase:
    rule_code: str
    matched_value: str
    unmatched_value: str
    measurement_kind: ObservationKind = "current"
    parameter: int | Decimal | None = None
    reference_kind: ObservationKind | None = None
    reference_value: str | None = None
    persisted: bool = False


CASES = (
    GoldenCase(
        "margin.discount_on_price_above_network",
        "12",
        "8",
        reference_kind="network_average",
        reference_value="10",
    ),
    GoldenCase(
        "margin.discount_on_price_increase",
        "12",
        "8",
        reference_kind="previous",
        reference_value="10",
    ),
    GoldenCase(
        "margin.gmroi_below_category",
        "1",
        "3",
        reference_kind="category_average",
        reference_value="2",
    ),
    GoldenCase(
        "margin.gmroi_below_network",
        "1",
        "3",
        reference_kind="network_average",
        reference_value="2",
    ),
    GoldenCase(
        "margin.gmroi_decline",
        "1",
        "3",
        reference_kind="previous",
        reference_value="2",
    ),
    GoldenCase(
        "margin.gross_percent_below_category",
        "15",
        "25",
        reference_kind="category_average",
        reference_value="20",
    ),
    GoldenCase(
        "margin.gross_percent_below_network",
        "15",
        "25",
        reference_kind="network_average",
        reference_value="20",
    ),
    GoldenCase(
        "margin.gross_percent_decline",
        "15",
        "25",
        reference_kind="previous",
        reference_value="20",
    ),
    GoldenCase(
        "margin.gross_profit_decline",
        "90",
        "110",
        reference_kind="previous",
        reference_value="100",
    ),
    GoldenCase(
        "margin.gross_profit_downward_trend",
        "-1",
        "0",
        measurement_kind="trend",
        parameter=2,
    ),
    GoldenCase("margin.gross_profit_negative", "-1", "0"),
    GoldenCase(
        "margin.gross_profit_persistent_negative",
        "-1",
        "1",
        persisted=True,
    ),
    GoldenCase(
        "margin.markup_below_category",
        "10",
        "30",
        reference_kind="category_average",
        reference_value="20",
    ),
    GoldenCase(
        "margin.markup_below_network",
        "10",
        "30",
        reference_kind="network_average",
        reference_value="20",
    ),
    GoldenCase(
        "margin.negative_margin_rate_above_network",
        "5",
        "1",
        reference_kind="network_average",
        reference_value="3",
    ),
    GoldenCase(
        "margin.negative_margin_rate_increase",
        "5",
        "1",
        reference_kind="previous",
        reference_value="3",
    ),
    GoldenCase("margin.negative_margin_rate_positive", "1", "0"),
    GoldenCase(
        "margin.price_dispersion_above_network",
        "12",
        "8",
        reference_kind="network_average",
        reference_value="10",
    ),
    GoldenCase(
        "margin.profit_per_sale_decline",
        "9",
        "11",
        reference_kind="previous",
        reference_value="10",
    ),
    GoldenCase(
        "margin.profit_per_unit_decline",
        "9",
        "11",
        reference_kind="previous",
        reference_value="10",
    ),
)


def _observation(
    kpi_code: str,
    value: str | None,
    *,
    kind: ObservationKind = "current",
    parameter: int | Decimal | None = None,
    period_start: datetime = WINDOW_START,
    period_end: datetime = WINDOW_END,
) -> KPIObservation:
    return KPIObservation(
        kpi_code=kpi_code,
        value=None if value is None else Decimal(value),
        kind=kind,
        parameter=parameter,
        quality_score=Decimal("1"),
        coverage=Decimal("1"),
        data_version=23,
        formula_version=1,
        lineage_ref=f"lineage://margin/{kpi_code.replace('.', '/')}/{kind}",
        period_start=period_start,
        period_end=period_end,
    )


def _negative_history(kpi_code: str) -> tuple[ObservationFrame, ...]:
    frames: list[ObservationFrame] = []
    for index in range(2):
        start = WINDOW_START - timedelta(days=14 - 7 * index)
        end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
        frames.append(
            ObservationFrame(
                (
                    _observation(
                        kpi_code,
                        "-1",
                        period_start=start,
                        period_end=end,
                    ),
                )
            )
        )
    return tuple(frames)


def _evaluation(case: GoldenCase, *, matched: bool) -> RuleEvaluationInput:
    rule = RULE_BY_CODE[case.rule_code]
    selected_value = case.matched_value if matched else case.unmatched_value
    observations: list[KPIObservation] = []
    if case.measurement_kind == "current":
        observations.append(_observation(rule.primary_kpi_code, selected_value))
    else:
        observations.extend(
            (
                _observation(rule.primary_kpi_code, "100"),
                _observation(
                    rule.primary_kpi_code,
                    selected_value,
                    kind=case.measurement_kind,
                    parameter=case.parameter,
                ),
            )
        )
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
        analytics_data_version=23,
        observations=tuple(observations),
        history=(_negative_history(rule.primary_kpi_code) if case.persisted else ()),
        evaluated_at=EVALUATED_AT,
        engine_version="2d-cp2-b2c.1",
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
        analytics_data_version=23,
        observations=(
            _observation(rule.primary_kpi_code, current),
            _observation(rule.primary_kpi_code, previous, kind="previous"),
        ),
        history=(),
        evaluated_at=EVALUATED_AT,
        engine_version="2d-cp2-b2c.1",
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


def _observation_by_key(evaluation: RuleEvaluationInput, key: str) -> KPIObservation:
    return next(item for item in evaluation.observations if item.measurement_key == key)


def test_margin_catalog_has_twenty_real_ordered_rules() -> None:
    assert len(MARGIN_RULES) == 20
    assert [rule.code for rule in MARGIN_RULES] == sorted(rule.code for rule in MARGIN_RULES)
    assert all(rule.domain == "margin" for rule in MARGIN_RULES)
    assert all(rule.status == "active" for rule in MARGIN_RULES)
    assert len({rule.code for rule in MARGIN_RULES}) == 20
    assert len({rule.rule_definition_id for rule in MARGIN_RULES}) == 20
    assert len({rule.to_snapshot().condition_hash for rule in MARGIN_RULES}) == 20
    assert len({rule.to_snapshot().definition_hash for rule in MARGIN_RULES}) == 20
    assert len({rule.governance_hash for rule in MARGIN_RULES}) == 20


def test_margin_rules_use_only_operational_margin_kpis_and_exact_actions() -> None:
    unavailable = {item.code for item in UNAVAILABLE_KPIS}
    for rule in MARGIN_RULES:
        validate_rule(rule)
        primary = KPI_BY_CODE[rule.primary_kpi_code]
        assert primary.category == "margin"
        assert set(rule.declared_kpi_codes).isdisjoint(unavailable)
        assert set(rule.dimensions) <= set(primary.dimensions)
        for reference in rule.actions:
            action = ACTION_BY_CODE[reference.action_code]
            assert action.domain == "margin"
            assert action.version == reference.action_version
            assert reference.suggested_priority == action.default_priority
            assert action.execution_mode == "human_review_required"
            assert action.allows_automatic_financial_execution is False


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.rule_code)
def test_every_margin_rule_has_matched_and_not_matched_golden_cases(case: GoldenCase) -> None:
    matched = evaluate_rule(_evaluation(case, matched=True))
    unmatched = evaluate_rule(_evaluation(case, matched=False))

    assert matched.state == "matched"
    assert matched.issue is None
    assert matched.diagnostic is not None
    assert matched.diagnostic.diagnostic_code == case.rule_code
    assert matched.evidence
    assert matched.hypotheses
    assert matched.recommendations
    assert unmatched.state == "not_matched"
    assert unmatched.issue is None
    assert unmatched.diagnostic is None
    assert unmatched.evidence == ()
    assert unmatched.recommendations == ()


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.rule_code)
def test_matched_margin_evidence_uses_observed_and_reference_values(case: GoldenCase) -> None:
    evaluation = _evaluation(case, matched=True)
    result = evaluate_rule(evaluation)
    rule = RULE_BY_CODE[case.rule_code]
    spec = rule.evidence[0]
    candidate = result.evidence[0]
    observation = _observation_by_key(evaluation, spec.observation_key)

    assert result.state == "matched"
    assert candidate.evidence_code == spec.evidence_code
    assert candidate.kpi_code == rule.primary_kpi_code
    assert candidate.observed_value == observation.value
    assert candidate.direction == spec.direction
    assert candidate.relation == "supports"
    if spec.reference_key is None:
        assert candidate.reference_value is None
    else:
        reference = _observation_by_key(evaluation, spec.reference_key)
        assert candidate.reference_value == reference.value


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.rule_code)
def test_margin_hypotheses_remain_separate_from_observed_facts(case: GoldenCase) -> None:
    rule = RULE_BY_CODE[case.rule_code]
    result = evaluate_rule(_evaluation(case, matched=True))

    assert result.state == "matched"
    assert result.hypotheses
    for hypothesis in rule.hypotheses:
        explanation = hypothesis.explanation.casefold()
        assert "pode" in explanation or "podem" in explanation
        assert "foi causado por" not in explanation
        assert "comprova que" not in explanation
        assert "é decorrente de" not in explanation
        assert all(hypothesis.explanation != evidence.detail for evidence in rule.evidence)
    assert all(
        item.evaluation_status in {"supported", "inconclusive"} for item in result.hypotheses
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.rule_code)
def test_all_matched_margin_recommendations_remain_advisory_only(case: GoldenCase) -> None:
    result = evaluate_rule(_evaluation(case, matched=True))

    assert result.state == "matched"
    for recommendation in result.recommendations:
        assert recommendation.execution_mode == "human_review_required"
        assert recommendation.requires_human_review is True
        assert recommendation.allows_automatic_financial_execution is False


@pytest.mark.parametrize(
    "case",
    tuple(case for case in CASES if case.reference_kind in {"network_average", "category_average"}),
    ids=lambda case: case.rule_code,
)
def test_missing_governed_margin_reference_is_skipped(case: GoldenCase) -> None:
    evaluation = _evaluation(case, matched=True)
    current_only = tuple(item for item in evaluation.observations if item.kind == "current")
    result = evaluate_rule(
        RuleEvaluationInput(
            rule=evaluation.rule,
            scope=evaluation.scope,
            window_start=evaluation.window_start,
            window_end=evaluation.window_end,
            analytics_data_version=evaluation.analytics_data_version,
            observations=current_only,
            history=evaluation.history,
            evaluated_at=evaluation.evaluated_at,
            engine_version=evaluation.engine_version,
        )
    )

    assert result.state == "skipped"
    assert result.issue is not None
    assert result.issue.code == "missing_kpi"
    assert result.diagnostic is None


def test_persistent_negative_profit_requires_two_complete_history_frames() -> None:
    case = next(
        item for item in CASES if item.rule_code == "margin.gross_profit_persistent_negative"
    )
    evaluation = _evaluation(case, matched=True)
    incomplete = RuleEvaluationInput(
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

    result = evaluate_rule(incomplete)

    assert result.state == "skipped"
    assert result.issue is not None
    assert result.issue.code == "condition_not_evaluable"


def test_persistent_negative_profit_does_not_match_after_current_recovery() -> None:
    case = next(
        item for item in CASES if item.rule_code == "margin.gross_profit_persistent_negative"
    )
    result = evaluate_rule(_evaluation(case, matched=False))

    assert result.state == "not_matched"
    assert result.issue is None
    assert result.diagnostic is None
    assert result.evidence == ()
    assert result.recommendations == ()


@pytest.mark.parametrize(
    ("rule_code", "operator"),
    DIRECTIONAL_CHANGE_RULES,
)
def test_directional_change_from_zero_is_evaluable(
    rule_code: str,
    operator: DirectionalOperator,
) -> None:
    current = "1" if operator == "gt" else "-1"
    result = evaluate_rule(_evaluation_with_previous(rule_code, current=current, previous="0"))

    assert result.state == "matched"
    assert result.issue is None


@pytest.mark.parametrize("rule_code", NEGATIVE_BASELINE_DECLINE_RULES)
@pytest.mark.parametrize(
    ("current", "expected_state"),
    (("-90", "not_matched"), ("-110", "matched")),
)
def test_decline_direction_has_no_negative_baseline_inversion(
    rule_code: str,
    current: str,
    expected_state: EvaluationState,
) -> None:
    result = evaluate_rule(_evaluation_with_previous(rule_code, current=current, previous="-100"))

    assert result.state == expected_state
    assert result.issue is None


@pytest.mark.parametrize(("rule_code", "expected_operator"), DIRECTIONAL_CHANGE_RULES)
def test_directional_margin_rules_use_absolute_change_ast(
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


def test_no_margin_rule_uses_percentage_change_only_as_a_directional_zero_test() -> None:
    for rule in MARGIN_RULES:
        for comparison in _comparison_nodes(rule.condition):
            directional_zero_test = (
                isinstance(comparison.right, Fixed)
                and comparison.right.value == Decimal("0")
                and comparison.op in {"lt", "gt"}
            )
            if directional_zero_test:
                assert not isinstance(comparison.left, PctChange)


def test_downward_profit_trend_uses_governed_parameterized_observation() -> None:
    case = next(item for item in CASES if item.rule_code == "margin.gross_profit_downward_trend")
    evaluation = _evaluation(case, matched=True)
    result = evaluate_rule(evaluation)

    assert result.state == "matched"
    assert result.evidence[0].observed_value == Decimal("-1")
    assert RULE_BY_CODE[case.rule_code].evidence[0].observation_key == (
        "trend:margin.gross_profit:2"
    )
    assert any(item.node_type == "compare" and item.outcome == "true" for item in result.trace)


def test_margin_manifest_is_deeply_immutable() -> None:
    manifest = catalog_manifest(MARGIN_RULES)
    first = manifest[0]

    assert isinstance(first, MappingProxyType)
    assert isinstance(first["dimensions"], tuple)
    assert isinstance(first["actions"], tuple)
    actions = first["actions"]
    assert isinstance(actions, tuple)
    assert isinstance(actions[0], MappingProxyType)
    with pytest.raises(TypeError):
        first["code"] = "margin.changed"  # type: ignore[index]


def test_margin_slice_and_global_catalog_have_explicit_golden_hashes() -> None:
    validate_catalog(RULE_CATALOG)
    assert catalog_hash(INVENTORY_RULES) == EXPECTED_INVENTORY_SLICE_HASH
    assert catalog_hash(SALES_RULES) == EXPECTED_SALES_SLICE_HASH
    assert catalog_hash(MARGIN_RULES) == EXPECTED_MARGIN_SLICE_HASH
    assert RULE_CATALOG_HASH == EXPECTED_GLOBAL_HASH
    assert len(RULE_CATALOG) == 120
    assert len(RULE_CATALOG_MANIFEST) == 120


def test_margin_catalog_is_stable_across_python_hash_seeds() -> None:
    repository = Path(__file__).parents[3]
    source = """
import json
from pharma_api.domain.diagnostics.rules import RULE_CATALOG, RULE_CATALOG_HASH
from pharma_api.domain.diagnostics.rules.margin import MARGIN_RULES
from pharma_api.domain.diagnostics.rules.validation import catalog_hash
print(json.dumps({
    "global_hash": RULE_CATALOG_HASH,
    "margin_hash": catalog_hash(MARGIN_RULES),
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
            cwd=repository,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        outputs.append(completed.stdout.strip())

    assert outputs[0] == outputs[1]
    payload = json.loads(outputs[0])
    assert payload["global_hash"] == EXPECTED_GLOBAL_HASH
    assert payload["margin_hash"] == EXPECTED_MARGIN_SLICE_HASH


def test_margin_rule_module_has_no_infrastructure_imports() -> None:
    path = (
        Path(__file__).parents[1]
        / "src"
        / "pharma_api"
        / "domain"
        / "diagnostics"
        / "rules"
        / "margin.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)

    forbidden = ("pharma_api.infrastructure", "sqlalchemy", "fastapi", "dramatiq", "redis")
    assert not any(marker in imported for marker in forbidden for imported in imports)
