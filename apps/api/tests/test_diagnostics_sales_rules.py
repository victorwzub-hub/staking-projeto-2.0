from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
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
from pharma_api.domain.diagnostics.rules import RULE_BY_CODE, RULE_CATALOG, RULE_CATALOG_HASH
from pharma_api.domain.diagnostics.rules.inventory import INVENTORY_RULES
from pharma_api.domain.diagnostics.rules.sales import SALES_RULES
from pharma_api.domain.diagnostics.rules.validation import (
    catalog_hash,
    validate_catalog,
    validate_rule,
)

TENANT_ID = UUID("10000000-0000-0000-0000-000000000201")
COMPANY_ID = UUID("20000000-0000-0000-0000-000000000201")
BRANCH_ID = UUID("30000000-0000-0000-0000-000000000201")
WINDOW_START = datetime(2026, 7, 8, tzinfo=UTC)
WINDOW_END = datetime(2026, 7, 14, 23, 59, 59, tzinfo=UTC)
EVALUATED_AT = datetime(2026, 7, 15, 8, tzinfo=UTC)
EXPECTED_INVENTORY_SLICE_HASH = "8417fe46225afc3990f2af0a0d4c95d8c8ac7b78294c40b48b3f349d0a4e52f7"
EXPECTED_SALES_SLICE_HASH = "b6bf16a32887f201481dfa085a2078afb9510aa42e39c1777ec532ce36eeb110"
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

ZERO_BASELINE_INCREASE_RULES = (
    "sales.average_discount_increase",
    "sales.cancellation_rate_increase",
    "sales.discount_rate_increase",
    "sales.return_rate_increase",
    "sales.top10_concentration_increase",
)

DIRECTIONAL_CHANGE_RULES: tuple[tuple[str, DirectionalOperator], ...] = (
    ("sales.active_product_count_decline", "lt"),
    ("sales.average_discount_increase", "gt"),
    ("sales.average_ticket_decline", "lt"),
    ("sales.cancellation_rate_increase", "gt"),
    ("sales.completed_count_decline", "lt"),
    ("sales.discount_rate_increase", "gt"),
    ("sales.items_per_sale_decline", "lt"),
    ("sales.net_revenue_decline", "lt"),
    ("sales.net_revenue_persistent_decline", "lt"),
    ("sales.return_rate_increase", "gt"),
    ("sales.top10_concentration_increase", "gt"),
    ("sales.units_sold_decline", "lt"),
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
        "sales.active_product_count_decline",
        "90",
        "100",
        reference_kind="previous",
        reference_value="100",
    ),
    GoldenCase(
        "sales.average_discount_increase",
        "110",
        "100",
        reference_kind="previous",
        reference_value="100",
    ),
    GoldenCase(
        "sales.average_ticket_below_network",
        "90",
        "100",
        reference_kind="network_average",
        reference_value="100",
    ),
    GoldenCase(
        "sales.average_ticket_decline",
        "90",
        "100",
        reference_kind="previous",
        reference_value="100",
    ),
    GoldenCase(
        "sales.cancellation_rate_above_network",
        "6",
        "5",
        reference_kind="network_average",
        reference_value="5",
    ),
    GoldenCase(
        "sales.cancellation_rate_increase",
        "6",
        "5",
        reference_kind="previous",
        reference_value="5",
    ),
    GoldenCase(
        "sales.completed_count_decline",
        "90",
        "100",
        reference_kind="previous",
        reference_value="100",
    ),
    GoldenCase(
        "sales.discount_rate_above_network",
        "12",
        "10",
        reference_kind="network_average",
        reference_value="10",
    ),
    GoldenCase(
        "sales.discount_rate_increase",
        "12",
        "10",
        reference_kind="previous",
        reference_value="10",
    ),
    GoldenCase(
        "sales.hourly_average_below_network",
        "90",
        "100",
        reference_kind="network_average",
        reference_value="100",
    ),
    GoldenCase(
        "sales.items_per_sale_decline",
        "90",
        "100",
        reference_kind="previous",
        reference_value="100",
    ),
    GoldenCase(
        "sales.net_revenue_below_network",
        "90",
        "100",
        reference_kind="network_average",
        reference_value="100",
    ),
    GoldenCase(
        "sales.net_revenue_decline", "90", "100", reference_kind="previous", reference_value="100"
    ),
    GoldenCase(
        "sales.net_revenue_downward_trend",
        "-1",
        "0",
        measurement_kind="trend",
        parameter=2,
    ),
    GoldenCase(
        "sales.net_revenue_persistent_decline",
        "90",
        "110",
        reference_kind="previous",
        reference_value="100",
        persisted=True,
    ),
    GoldenCase(
        "sales.return_rate_above_network",
        "4",
        "3",
        reference_kind="network_average",
        reference_value="3",
    ),
    GoldenCase(
        "sales.return_rate_increase", "4", "3", reference_kind="previous", reference_value="3"
    ),
    GoldenCase(
        "sales.revenue_per_product_below_category",
        "90",
        "100",
        reference_kind="category_average",
        reference_value="100",
    ),
    GoldenCase(
        "sales.top10_concentration_increase",
        "60",
        "50",
        reference_kind="previous",
        reference_value="50",
    ),
    GoldenCase(
        "sales.units_sold_decline", "90", "100", reference_kind="previous", reference_value="100"
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
        data_version=22,
        formula_version=1,
        lineage_ref=f"lineage://sales/{kpi_code.replace('.', '/')}/{kind}",
        period_start=period_start,
        period_end=period_end,
    )


def _decline_history(kpi_code: str) -> tuple[ObservationFrame, ...]:
    frames: list[ObservationFrame] = []
    for index in range(2):
        start = WINDOW_START - timedelta(days=14 - 7 * index)
        end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
        frames.append(
            ObservationFrame(
                (
                    _observation(
                        kpi_code,
                        "90",
                        period_start=start,
                        period_end=end,
                    ),
                    _observation(
                        kpi_code,
                        "100",
                        kind="previous",
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
        analytics_data_version=22,
        observations=tuple(observations),
        history=(_decline_history(rule.primary_kpi_code) if case.persisted else ()),
        evaluated_at=EVALUATED_AT,
        engine_version="2d-cp2-b2b.1",
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
        analytics_data_version=22,
        observations=(
            _observation(rule.primary_kpi_code, current),
            _observation(rule.primary_kpi_code, previous, kind="previous"),
        ),
        history=(),
        evaluated_at=EVALUATED_AT,
        engine_version="2d-cp2-b2b.1",
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


def test_sales_catalog_has_twenty_real_ordered_rules() -> None:
    assert len(SALES_RULES) == 20
    assert [rule.code for rule in SALES_RULES] == sorted(rule.code for rule in SALES_RULES)
    assert all(rule.domain == "sales" for rule in SALES_RULES)
    assert all(rule.status == "active" for rule in SALES_RULES)
    assert len({rule.rule_definition_id for rule in SALES_RULES}) == 20
    assert len({rule.governance_hash for rule in SALES_RULES}) == 20
    assert len({rule.to_snapshot().definition_hash for rule in SALES_RULES}) == 20


def test_sales_rules_use_only_operational_sales_kpis_and_exact_actions() -> None:
    unavailable = {item.code for item in UNAVAILABLE_KPIS}
    for rule in SALES_RULES:
        validate_rule(rule)
        assert rule.primary_kpi_code in KPI_BY_CODE
        assert KPI_BY_CODE[rule.primary_kpi_code].category == "sales"
        assert set(rule.declared_kpi_codes).isdisjoint(unavailable)
        for reference in rule.actions:
            action = ACTION_BY_CODE[reference.action_code]
            assert action.domain == "sales"
            assert action.version == reference.action_version
            assert reference.suggested_priority == action.default_priority
            assert action.execution_mode == "human_review_required"
            assert action.allows_automatic_financial_execution is False


@pytest.mark.parametrize("rule_code", ZERO_BASELINE_INCREASE_RULES)
def test_adverse_increase_from_zero_is_matched_instead_of_skipped(rule_code: str) -> None:
    result = evaluate_rule(_evaluation_with_previous(rule_code, current="1", previous="0"))

    assert result.state == "matched"
    assert result.issue is None


@pytest.mark.parametrize(
    ("current", "expected_state"),
    (("-90", "not_matched"), ("-110", "matched")),
)
def test_revenue_decline_uses_absolute_direction_with_negative_baseline(
    current: str,
    expected_state: Literal["matched", "not_matched"],
) -> None:
    result = evaluate_rule(
        _evaluation_with_previous(
            "sales.net_revenue_decline",
            current=current,
            previous="-100",
        )
    )

    assert result.state == expected_state
    assert result.issue is None


@pytest.mark.parametrize(("rule_code", "expected_operator"), DIRECTIONAL_CHANGE_RULES)
def test_directional_change_rules_use_absolute_change_ast(
    rule_code: str,
    expected_operator: DirectionalOperator,
) -> None:
    condition = RULE_BY_CODE[rule_code].condition
    comparisons = _comparison_nodes(condition)
    expected_comparison_count = 2 if rule_code == "sales.net_revenue_persistent_decline" else 1

    assert len(comparisons) == expected_comparison_count
    assert "abs_change" in _node_types(condition.as_json())
    assert "pct_change" not in _node_types(condition.as_json())
    for comparison in comparisons:
        assert isinstance(comparison.left, AbsChange)
        assert not isinstance(comparison.left, PctChange)
        assert comparison.left.baseline == "previous"
        assert comparison.op == expected_operator
        assert isinstance(comparison.right, Fixed)
        assert comparison.right.value == Decimal("0")


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.rule_code)
def test_every_sales_rule_has_matched_and_not_matched_golden_cases(case: GoldenCase) -> None:
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
def test_matched_sales_evidence_uses_the_observed_and_reference_values(case: GoldenCase) -> None:
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
def test_sales_hypotheses_remain_separate_from_observed_facts(case: GoldenCase) -> None:
    rule = RULE_BY_CODE[case.rule_code]
    result = evaluate_rule(_evaluation(case, matched=True))

    assert result.state == "matched"
    assert result.hypotheses
    for hypothesis in rule.hypotheses:
        assert (
            "pode" in hypothesis.explanation.casefold()
            or "podem" in hypothesis.explanation.casefold()
        )
        assert all(hypothesis.explanation != evidence.detail for evidence in rule.evidence)
    assert all(
        item.evaluation_status in {"supported", "inconclusive"} for item in result.hypotheses
    )


def test_persistent_revenue_decline_requires_two_complete_history_frames() -> None:
    case = next(item for item in CASES if item.rule_code == "sales.net_revenue_persistent_decline")
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


def test_persistent_revenue_decline_does_not_match_after_current_recovery() -> None:
    case = next(item for item in CASES if item.rule_code == "sales.net_revenue_persistent_decline")
    result = evaluate_rule(_evaluation(case, matched=False))

    assert result.state == "not_matched"
    assert result.issue is None
    assert result.diagnostic is None
    assert result.evidence == ()
    assert result.recommendations == ()


def test_downward_trend_uses_the_governed_parameterized_observation() -> None:
    case = next(item for item in CASES if item.rule_code == "sales.net_revenue_downward_trend")
    evaluation = _evaluation(case, matched=True)
    result = evaluate_rule(evaluation)

    assert result.state == "matched"
    assert result.evidence[0].observed_value == Decimal("-1")
    assert RULE_BY_CODE[case.rule_code].evidence[0].observation_key == "trend:sales.net_revenue:2"
    assert any(item.node_type == "compare" and item.outcome == "true" for item in result.trace)


def test_sales_extension_preserves_the_approved_inventory_slice() -> None:
    assert len(INVENTORY_RULES) == 20
    assert catalog_hash(INVENTORY_RULES) == EXPECTED_INVENTORY_SLICE_HASH
    assert all(rule.domain == "inventory" for rule in INVENTORY_RULES)


def test_sales_slice_has_explicit_golden_hash() -> None:
    assert catalog_hash(SALES_RULES) == EXPECTED_SALES_SLICE_HASH


def test_full_catalog_is_valid_ordered_and_has_the_new_golden_hash() -> None:
    validate_catalog(RULE_CATALOG)
    assert len(RULE_CATALOG) == 120
    assert RULE_CATALOG_HASH == EXPECTED_GLOBAL_HASH
    assert [rule.code for rule in RULE_CATALOG] == sorted(rule.code for rule in RULE_CATALOG)
    assert len({rule.code for rule in RULE_CATALOG}) == 120
    assert len({rule.rule_definition_id for rule in RULE_CATALOG}) == 120
    assert len({rule.governance_hash for rule in RULE_CATALOG}) == 120
    assert len({rule.to_snapshot().definition_hash for rule in RULE_CATALOG}) == 120


def test_catalog_is_stable_across_python_hash_seeds() -> None:
    repository = Path(__file__).parents[3]
    source = """
import json
from pharma_api.domain.diagnostics.rules import RULE_CATALOG, RULE_CATALOG_HASH
print(json.dumps({
    "hash": RULE_CATALOG_HASH,
    "codes": [rule.code for rule in RULE_CATALOG],
    "uuids": [str(rule.rule_definition_id) for rule in RULE_CATALOG],
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
    assert json.loads(outputs[0])["hash"] == EXPECTED_GLOBAL_HASH
