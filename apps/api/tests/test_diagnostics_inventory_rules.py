from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

import pytest

from pharma_api.domain.diagnostics.engine import (
    EvaluationScope,
    KPIObservation,
    ObservationFrame,
    RuleEvaluationInput,
    evaluate_rule,
)
from pharma_api.domain.diagnostics.rules import RULE_BY_CODE, RULE_CATALOG

TENANT_ID = UUID("10000000-0000-0000-0000-000000000101")
COMPANY_ID = UUID("20000000-0000-0000-0000-000000000101")
BRANCH_ID = UUID("30000000-0000-0000-0000-000000000101")
WINDOW_START = datetime(2026, 7, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 7, 7, 23, 59, 59, tzinfo=UTC)
EVALUATED_AT = datetime(2026, 7, 8, 8, tzinfo=UTC)
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


@dataclass(frozen=True, slots=True)
class GoldenCase:
    rule_code: str
    matched_current: str
    unmatched_current: str
    reference_kind: ObservationKind | None = None
    reference_value: str | None = None
    persisted: bool = False


CASES = (
    GoldenCase("inventory.excess_products", "1", "0"),
    GoldenCase("inventory.expired_lots", "1", "0"),
    GoldenCase("inventory.expiring_lots", "1", "0"),
    GoldenCase("inventory.high_coverage", "91", "90"),
    GoldenCase("inventory.low_coverage", "6", "7"),
    GoldenCase("inventory.negative_stock", "1", "0"),
    GoldenCase(
        "inventory.negative_stock_above_network",
        "2",
        "1",
        "network_average",
        "1",
    ),
    GoldenCase("inventory.no_sale_stock", "1", "0"),
    GoldenCase("inventory.observed_stockout", "1", "0"),
    GoldenCase("inventory.recurring_stockout", "1", "0", persisted=True),
    GoldenCase("inventory.slow_moving_coverage", "61", "60"),
    GoldenCase("inventory.stock_adjustments", "1", "0"),
    GoldenCase("inventory.stock_adjustments_worsening", "2", "1", "previous", "1"),
    GoldenCase("inventory.stock_damage", "1", "0"),
    GoldenCase("inventory.stock_loss", "1", "0"),
    GoldenCase("inventory.stockout_above_network", "2", "1", "network_average", "1"),
    GoldenCase("inventory.stockout_risk", "1", "0"),
    GoldenCase(
        "inventory.stockout_risk_above_network",
        "2",
        "1",
        "network_average",
        "1",
    ),
    GoldenCase("inventory.stockout_worsening", "2", "1", "previous", "1"),
    GoldenCase("inventory.weak_sell_through", "1", "2", "category_average", "2"),
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
        data_version=21,
        formula_version=1,
        lineage_ref=f"lineage://inventory/{kpi_code.replace('.', '/')}",
        period_start=period_start,
        period_end=period_end,
    )


def _history(kpi_code: str, *, matched: bool) -> tuple[ObservationFrame, ...]:
    frames: list[ObservationFrame] = []
    values = ("1", "1") if matched else ("1", "0")
    for index, value in enumerate(values):
        start = WINDOW_START - timedelta(days=14 - 7 * index)
        end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
        frames.append(
            ObservationFrame(
                (
                    _observation(
                        kpi_code,
                        value,
                        period_start=start,
                        period_end=end,
                    ),
                )
            )
        )
    return tuple(frames)


def _evaluation(case: GoldenCase, *, matched: bool) -> RuleEvaluationInput:
    rule = RULE_BY_CODE[case.rule_code]
    current_value = case.matched_current if matched else case.unmatched_current
    observations = [_observation(rule.primary_kpi_code, current_value)]
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
        analytics_data_version=21,
        observations=tuple(observations),
        history=(_history(rule.primary_kpi_code, matched=matched) if case.persisted else ()),
        evaluated_at=EVALUATED_AT,
        engine_version="2d-cp2-b2a.1",
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.rule_code)
def test_every_inventory_rule_has_matched_and_not_matched_golden_cases(
    case: GoldenCase,
) -> None:
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
    assert unmatched.recommendations == ()


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.rule_code)
def test_all_matched_rules_remain_advisory_only(case: GoldenCase) -> None:
    result = evaluate_rule(_evaluation(case, matched=True))

    assert result.state == "matched"
    for recommendation in result.recommendations:
        assert recommendation.execution_mode == "human_review_required"
        assert recommendation.requires_human_review is True
        assert recommendation.allows_automatic_financial_execution is False


def test_missing_governed_comparison_reference_is_skipped_not_invented() -> None:
    case = next(item for item in CASES if item.rule_code == "inventory.stockout_above_network")
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


def test_persisted_rule_is_indeterminate_without_two_history_frames() -> None:
    case = next(item for item in CASES if item.rule_code == "inventory.recurring_stockout")
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


def test_recurring_stockout_does_not_match_after_current_recovery() -> None:
    case = next(item for item in CASES if item.rule_code == "inventory.recurring_stockout")
    matched = _evaluation(case, matched=True)
    recovered = RuleEvaluationInput(
        rule=matched.rule,
        scope=matched.scope,
        window_start=matched.window_start,
        window_end=matched.window_end,
        analytics_data_version=matched.analytics_data_version,
        observations=(_observation("inventory.zero_stock_rate", "0"),),
        history=matched.history,
        evaluated_at=matched.evaluated_at,
        engine_version=matched.engine_version,
    )

    result = evaluate_rule(recovered)

    assert result.state == "not_matched"
    assert result.issue is None
    assert result.diagnostic is None
    assert result.evidence == ()
    assert result.recommendations == ()


def test_representative_result_hashes_are_golden_and_repeatable() -> None:
    expected = {
        "inventory.low_coverage": (
            "bfafcc6d85b0e186e4b9597f58b2bf1fd8a3ef11bd8f0626a1124e547aa67a84"
        ),
        "inventory.observed_stockout": (
            "50dfd35a50b2e0da75351d4844242c28e6829d08f3c52b94dcd9739a1bd49955"
        ),
        "inventory.recurring_stockout": (
            "f15ee61b42058c80478a0d19e782365bae60cc7a97a0f906a1c2ea8845230eb5"
        ),
        "inventory.stockout_above_network": (
            "c3c061c697a3a6fca6a238f68f48b15c33659173bfddb8338eeaec878a71a7a1"
        ),
    }

    for code, result_hash in expected.items():
        case = next(item for item in CASES if item.rule_code == code)
        first = evaluate_rule(_evaluation(case, matched=True))
        second = evaluate_rule(_evaluation(case, matched=True))
        assert first == second
        assert first.result_hash == second.result_hash
        assert first.result_hash == result_hash


def test_rule_catalog_covers_all_golden_cases_exactly_once() -> None:
    assert {case.rule_code for case in CASES} == {rule.code for rule in RULE_CATALOG}
    assert len({case.rule_code for case in CASES}) == len(CASES)
