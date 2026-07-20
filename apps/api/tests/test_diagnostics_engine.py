from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID

import pytest

import pharma_api.domain.diagnostics.engine as engine_module
from pharma_api.domain.diagnostics.engine import (
    ActionReference,
    CanonicalizationError,
    DiagnosticEngineValidationError,
    EvaluationScope,
    EvidenceSpec,
    HypothesisSpec,
    KPIObservation,
    ObservationFrame,
    RuleEvaluationInput,
    RuleSnapshot,
    canonical_json,
    canonical_sha256,
    evaluate_rule,
)

TENANT_ID = UUID("10000000-0000-0000-0000-000000000001")
OTHER_TENANT_ID = UUID("10000000-0000-0000-0000-000000000002")
COMPANY_ID = UUID("20000000-0000-0000-0000-000000000001")
BRANCH_ID = UUID("30000000-0000-0000-0000-000000000001")
RULE_ID = UUID("40000000-0000-0000-0000-000000000001")
WINDOW_START = datetime(2026, 7, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 7, 7, 23, 59, 59, tzinfo=UTC)
EVALUATED_AT = datetime(2026, 7, 8, 8, tzinfo=UTC)


def _condition() -> dict[str, object]:
    return {
        "type": "all_of",
        "nodes": [
            {
                "type": "compare",
                "left": {"type": "kpi", "kpi_code": "sales.net_revenue"},
                "op": "lt",
                "right": {"type": "previous", "kpi_code": "sales.net_revenue"},
            },
            {
                "type": "data_available",
                "kpi_code": "sales.net_revenue",
                "min_coverage": "0.80",
            },
        ],
    }


def _observation(
    value: str | None,
    *,
    kind: Literal[
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
    ] = "current",
    quality: str = "1",
    coverage: str = "1",
    data_version: int = 11,
    lineage: str | None = "lineage://sales/net-revenue",
    period_start: datetime = WINDOW_START,
    period_end: datetime = WINDOW_END,
) -> KPIObservation:
    return KPIObservation(
        kpi_code="sales.net_revenue",
        value=None if value is None else Decimal(value),
        kind=kind,
        quality_score=Decimal(quality),
        coverage=Decimal(coverage),
        data_version=data_version,
        lineage_ref=lineage,
        period_start=period_start,
        period_end=period_end,
    )


def _rule(
    *,
    condition: object | None = None,
    evidence: tuple[EvidenceSpec, ...] | None = None,
    actions: tuple[ActionReference, ...] | None = None,
    hypotheses: tuple[HypothesisSpec, ...] | None = None,
    declared_kpis: tuple[str, ...] = ("sales.net_revenue",),
    ownership_type: Literal["system", "tenant"] = "system",
    rule_tenant_id: UUID | None = None,
    condition_hash: str | None = None,
    definition_hash: str | None = None,
    base_severity: Literal["info", "low", "medium", "high", "critical"] = "high",
) -> RuleSnapshot:
    evidence_items = (
        (
            EvidenceSpec(
                evidence_code="sales.revenue_drop",
                evidence_type="comparison",
                kpi_code="sales.net_revenue",
                observation_key="sales.net_revenue",
                reference_key="previous:sales.net_revenue",
                direction="below",
                relation="supports",
                weight=Decimal("1"),
                detail="Receita líquida abaixo do período anterior.",
            ),
        )
        if evidence is None
        else evidence
    )
    action_items = (
        (
            ActionReference(
                action_code="sales.revenue_drop_review",
                action_version=1,
                rationale="Revisar a causa observável da queda antes de qualquer intervenção.",
            ),
        )
        if actions is None
        else actions
    )
    hypothesis_items = (
        (
            HypothesisSpec(
                hypothesis_code="sales.demand_contraction",
                explanation="A demanda pode ter recuado; a hipótese não é tratada como fato.",
                supporting_evidence_codes=("sales.revenue_drop",),
            ),
        )
        if hypotheses is None
        else hypotheses
    )
    return RuleSnapshot.from_documents(
        rule_definition_id=RULE_ID,
        version_number=1,
        ownership_type=ownership_type,
        rule_tenant_id=rule_tenant_id,
        diagnostic_code="sales.revenue_decline",
        domain="sales",
        title="Queda de receita líquida",
        summary="A receita líquida ficou abaixo da referência governada.",
        base_severity=base_severity,
        primary_kpi_code="sales.net_revenue",
        condition_document=_condition() if condition is None else condition,
        declared_kpi_codes=declared_kpis,
        controls_document={},
        actions=action_items,
        evidence=evidence_items,
        hypotheses=hypothesis_items,
        condition_hash=condition_hash,
        definition_hash=definition_hash,
    )


def _evaluation(
    *,
    rule: RuleSnapshot | None = None,
    observations: tuple[KPIObservation, ...] | None = None,
    scope: EvaluationScope | None = None,
    history: tuple[ObservationFrame, ...] = (),
    data_version: int = 11,
) -> RuleEvaluationInput:
    return RuleEvaluationInput(
        rule=rule or _rule(),
        scope=scope or EvaluationScope(TENANT_ID, "tenant"),
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        analytics_data_version=data_version,
        observations=(
            (
                _observation("80"),
                _observation("100", kind="previous"),
            )
            if observations is None
            else observations
        ),
        history=history,
        evaluated_at=EVALUATED_AT,
        engine_version="2d-cp2-b1.1",
    )


def test_matched_rule_produces_diagnostic_evidence_hypothesis_and_advisory_action() -> None:
    result = evaluate_rule(_evaluation())

    assert result.state == "matched"
    assert result.issue is None
    assert result.diagnostic is not None
    assert result.diagnostic.diagnostic_code == "sales.revenue_decline"
    assert result.diagnostic.observed_value == Decimal("80")
    assert result.diagnostic.reference_value == Decimal("100")
    assert result.evidence[0].relation == "supports"
    assert result.hypotheses[0].evaluation_status == "supported"
    assert "pode" in result.hypotheses[0].explanation
    assert result.recommendations[0].execution_mode == "human_review_required"
    assert result.recommendations[0].requires_human_review is True
    assert result.recommendations[0].allows_automatic_financial_execution is False


def test_same_semantic_input_and_different_observation_order_are_identical() -> None:
    evaluation = _evaluation()
    first = evaluate_rule(evaluation)
    second = evaluate_rule(
        replace(evaluation, observations=tuple(reversed(evaluation.observations)))
    )

    assert first == second
    assert first.canonical_payload() == second.canonical_payload()
    assert first.result_hash == second.result_hash
    assert first.fingerprint == second.fingerprint


def test_condition_key_order_does_not_change_hash_or_result() -> None:
    original = _condition()
    reordered: dict[str, object] = {
        "nodes": cast(list[object], original["nodes"]),
        "type": "all_of",
    }
    first_rule = _rule(condition=_condition())
    second_rule = _rule(condition=reordered)

    assert first_rule.condition_hash == second_rule.condition_hash
    assert first_rule.definition_hash == second_rule.definition_hash
    assert evaluate_rule(_evaluation(rule=first_rule)) == evaluate_rule(
        _evaluation(rule=second_rule)
    )


def test_not_matched_is_distinct_from_skipped_or_failed() -> None:
    result = evaluate_rule(
        _evaluation(observations=(_observation("120"), _observation("100", kind="previous")))
    )

    assert result.state == "not_matched"
    assert result.diagnostic is None
    assert result.issue is None
    assert result.trace[0].outcome == "false"


def test_nested_boolean_condition_has_stable_explainability_trace() -> None:
    nested = {
        "type": "all_of",
        "nodes": [
            _condition(),
            {
                "type": "negate",
                "node": {"type": "missing_data", "kpi_code": "sales.net_revenue"},
            },
        ],
    }

    result = evaluate_rule(_evaluation(rule=_rule(condition=nested)))

    assert result.state == "matched"
    assert [entry.path for entry in result.trace] == [
        "$",
        "$.nodes[0]",
        "$.nodes[0].nodes[0]",
        "$.nodes[0].nodes[1]",
        "$.nodes[1]",
        "$.nodes[1].node",
    ]
    json.dumps(result.as_dict(), default=str)


def test_unknown_declared_kpi_is_a_structured_rule_failure() -> None:
    result = evaluate_rule(_evaluation(rule=_rule(declared_kpis=("sales.net_revenue", "x.nope"))))

    assert result.state == "failed"
    assert result.issue is not None
    assert result.issue.code == "unknown_kpi"


def test_missing_required_measurement_is_skipped_with_stable_code() -> None:
    result = evaluate_rule(_evaluation(observations=(_observation("80"),)))

    assert result.state == "skipped"
    assert result.issue is not None
    assert result.issue.code == "missing_kpi"


def test_indeterminate_condition_is_not_reported_as_not_matched() -> None:
    result = evaluate_rule(
        _evaluation(observations=(_observation(None), _observation("100", kind="previous")))
    )

    assert result.state == "skipped"
    assert result.issue is not None
    assert result.issue.code == "condition_not_evaluable"


def test_float_observation_values_are_rejected() -> None:
    with pytest.raises(DiagnosticEngineValidationError, match="Decimal"):
        KPIObservation(
            kpi_code="sales.net_revenue",
            value=cast(Decimal, 80.1),
            period_start=WINDOW_START,
            period_end=WINDOW_END,
            data_version=11,
        )


@pytest.mark.parametrize(
    "scope",
    [
        EvaluationScope(TENANT_ID, "tenant"),
        EvaluationScope(TENANT_ID, "company", company_id=COMPANY_ID),
        EvaluationScope(
            TENANT_ID,
            "branch",
            company_id=COMPANY_ID,
            branch_id=BRANCH_ID,
        ),
    ],
)
def test_all_three_scope_shapes_are_supported(scope: EvaluationScope) -> None:
    assert evaluate_rule(_evaluation(scope=scope)).state == "matched"


@pytest.mark.parametrize(
    ("scope_type", "company_id", "branch_id"),
    [
        ("tenant", COMPANY_ID, None),
        ("company", None, None),
        ("branch", COMPANY_ID, None),
    ],
)
def test_incoherent_scope_is_rejected(
    scope_type: Literal["tenant", "company", "branch"],
    company_id: UUID | None,
    branch_id: UUID | None,
) -> None:
    with pytest.raises(DiagnosticEngineValidationError, match="invalid_scope"):
        EvaluationScope(
            TENANT_ID,
            scope_type,
            company_id=company_id,
            branch_id=branch_id,
        )


def test_invalid_window_is_rejected_before_evaluation() -> None:
    with pytest.raises(DiagnosticEngineValidationError, match="window_mismatch"):
        replace(_evaluation(), window_start=WINDOW_END, window_end=WINDOW_START)


def test_observation_outside_window_is_skipped() -> None:
    result = evaluate_rule(
        _evaluation(
            observations=(
                _observation(
                    "80",
                    period_start=datetime(2026, 6, 30, tzinfo=UTC),
                ),
                _observation("100", kind="previous"),
            )
        )
    )

    assert result.state == "skipped"
    assert result.issue is not None
    assert result.issue.code == "window_mismatch"


def test_data_version_mismatch_is_skipped() -> None:
    result = evaluate_rule(
        _evaluation(
            observations=(_observation("80", data_version=10), _observation("100", kind="previous"))
        )
    )

    assert result.state == "skipped"
    assert result.issue is not None
    assert result.issue.code == "data_version_mismatch"


def test_insufficient_quality_prevents_a_diagnosis() -> None:
    result = evaluate_rule(
        _evaluation(
            observations=(
                _observation("80", quality="0.10"),
                _observation("100", kind="previous", quality="0.10"),
            )
        )
    )

    assert result.state == "skipped"
    assert result.issue is not None
    assert result.issue.code == "insufficient_data_quality"


def test_contradicting_evidence_reduces_confidence() -> None:
    support = EvidenceSpec(
        evidence_code="sales.revenue_drop",
        evidence_type="comparison",
        kpi_code="sales.net_revenue",
        observation_key="sales.net_revenue",
        reference_key="previous:sales.net_revenue",
        direction="below",
        relation="supports",
        weight=Decimal("1"),
    )
    contradiction = EvidenceSpec(
        evidence_code="sales.revenue_recovery_signal",
        evidence_type="trend",
        kpi_code="sales.net_revenue",
        observation_key="sales.net_revenue",
        direction="increasing",
        relation="contradicts",
        weight=Decimal("1"),
    )
    without_contradiction = evaluate_rule(
        _evaluation(rule=_rule(evidence=(support,), hypotheses=()))
    )
    with_contradiction = evaluate_rule(
        _evaluation(rule=_rule(evidence=(support, contradiction), hypotheses=()))
    )

    assert without_contradiction.diagnostic is not None
    assert with_contradiction.diagnostic is not None
    assert (
        with_contradiction.diagnostic.confidence_score
        < without_contradiction.diagnostic.confidence_score
    )


def test_confidence_is_bounded_and_reaches_governed_upper_limit() -> None:
    result = evaluate_rule(_evaluation())

    assert result.diagnostic is not None
    assert result.diagnostic.confidence_score == Decimal("1.0000")
    assert Decimal("0") <= result.diagnostic.confidence_score <= Decimal("1")


def test_priority_is_deterministic_and_uses_severity_action_impact_and_confidence() -> None:
    action = ActionReference(
        action_code="inventory.coverage_review",
        action_version=1,
        rationale="Revisar os parâmetros de cobertura sob autorização humana.",
    )
    evidence = EvidenceSpec(
        evidence_code="sales.revenue_drop",
        evidence_type="comparison",
        kpi_code="sales.net_revenue",
        observation_key="sales.net_revenue",
        reference_key="previous:sales.net_revenue",
        direction="below",
    )
    high = evaluate_rule(
        _evaluation(rule=_rule(actions=(action,), evidence=(evidence,), base_severity="low"))
    )
    low = evaluate_rule(
        _evaluation(
            rule=_rule(actions=(action,), evidence=(evidence,), base_severity="low"),
            observations=(
                _observation("80", quality="0.30", coverage="0.90", lineage=None),
                _observation("100", kind="previous", quality="0.30", coverage="0.90", lineage=None),
            ),
        )
    )

    assert high.diagnostic is not None
    assert low.diagnostic is not None
    assert high.diagnostic.priority == 1
    assert low.diagnostic.priority == 3


def test_fingerprint_changes_only_for_semantic_input_changes() -> None:
    original = evaluate_rule(_evaluation())
    reordered = evaluate_rule(_evaluation(observations=tuple(reversed(_evaluation().observations))))
    changed = evaluate_rule(
        _evaluation(observations=(_observation("79"), _observation("100", kind="previous")))
    )

    assert original.fingerprint == reordered.fingerprint
    assert original.fingerprint != changed.fingerprint
    assert original.fingerprint is not None
    assert len(original.fingerprint) == 64


@pytest.mark.parametrize(
    "reference",
    [
        ActionReference("sales.not_allowed", 1, "Ação inexistente."),
        ActionReference("sales.revenue_drop_review", 999, "Versão não governada."),
    ],
)
def test_unknown_or_wrong_action_version_is_blocked(reference: ActionReference) -> None:
    result = evaluate_rule(_evaluation(rule=_rule(actions=(reference,))))

    assert result.state == "failed"
    assert result.issue is not None
    assert result.issue.code == "action_not_allowed"
    assert result.recommendations == ()


def test_tenant_owned_rule_cannot_evaluate_for_another_tenant() -> None:
    rule = _rule(ownership_type="tenant", rule_tenant_id=OTHER_TENANT_ID)

    result = evaluate_rule(_evaluation(rule=rule))

    assert result.state == "failed"
    assert result.issue is not None
    assert result.issue.code == "invalid_scope"


def test_persisted_condition_consumes_history_without_requiring_current_baseline() -> None:
    condition = {
        "type": "persisted",
        "periods": 2,
        "predicate": {
            "type": "compare",
            "left": {"type": "kpi", "kpi_code": "sales.net_revenue"},
            "op": "lt",
            "right": {"type": "previous", "kpi_code": "sales.net_revenue"},
        },
    }
    history = (
        ObservationFrame((_observation("90"), _observation("100", kind="previous"))),
        ObservationFrame((_observation("80"), _observation("90", kind="previous"))),
    )
    rule = _rule(condition=condition, evidence=(), hypotheses=())

    result = evaluate_rule(
        _evaluation(rule=rule, observations=(_observation("80"),), history=history)
    )

    assert result.state == "matched"


def test_irrelevant_observation_kind_does_not_change_confidence_or_fingerprint() -> None:
    baseline = evaluate_rule(_evaluation())
    extra_goal = KPIObservation(
        kpi_code="sales.net_revenue",
        value=Decimal("999"),
        period_start=WINDOW_START,
        period_end=WINDOW_END,
        data_version=11,
        kind="goal",
        quality_score=Decimal("0"),
        coverage=Decimal("0"),
        lineage_ref=None,
    )
    enriched = evaluate_rule(_evaluation(observations=(*_evaluation().observations, extra_goal)))

    assert baseline.diagnostic is not None
    assert enriched.diagnostic is not None
    assert baseline.diagnostic.confidence_score == enriched.diagnostic.confidence_score
    assert baseline.fingerprint == enriched.fingerprint


def test_missing_data_rule_can_match_explicit_absence_even_with_zero_quality() -> None:
    condition = {"type": "missing_data", "kpi_code": "sales.net_revenue"}
    evidence = (
        EvidenceSpec(
            evidence_code="operations.missing_revenue",
            evidence_type="data_quality",
            kpi_code="sales.net_revenue",
            observation_key="sales.net_revenue",
            direction="not_applicable",
            relation="supports",
            detail="Ausência explícita do KPI no período avaliado.",
        ),
    )
    rule = _rule(condition=condition, evidence=evidence, hypotheses=())
    absent = _observation(None, quality="0", coverage="0", lineage=None)

    result = evaluate_rule(_evaluation(rule=rule, observations=(absent,)))

    assert result.state == "matched"
    assert result.diagnostic is not None
    assert result.diagnostic.observed_value is None
    assert result.evidence[0].observed_value is None


def test_malformed_serialized_snapshot_is_a_structured_validation_failure() -> None:
    malformed = replace(_rule(), condition_json="{")

    result = evaluate_rule(_evaluation(rule=malformed))

    assert result.state == "failed"
    assert result.issue is not None
    assert result.issue.code == "invalid_rule_snapshot"


def test_invalid_action_is_rejected_even_when_predicate_would_not_match() -> None:
    invalid = ActionReference("sales.not_allowed", 1, "Ação inexistente.")
    rule = _rule(actions=(invalid,))
    observations = (_observation("120"), _observation("100", kind="previous"))

    result = evaluate_rule(_evaluation(rule=rule, observations=observations))

    assert result.state == "failed"
    assert result.issue is not None
    assert result.issue.code == "action_not_allowed"


def test_evidence_cannot_relabel_an_observation_from_another_kpi() -> None:
    evidence = (
        EvidenceSpec(
            evidence_code="inventory.mislabeled_revenue",
            evidence_type="comparison",
            kpi_code="inventory.zero_stock_rate",
            observation_key="sales.net_revenue",
            direction="below",
            relation="supports",
            detail="Contrato inválido usado somente no teste.",
        ),
    )
    rule = _rule(
        evidence=evidence,
        hypotheses=(),
        declared_kpis=("sales.net_revenue", "inventory.zero_stock_rate"),
    )

    result = evaluate_rule(_evaluation(rule=rule))

    assert result.state == "skipped"
    assert result.issue is not None
    assert result.issue.code == "invalid_rule_snapshot"


def test_declared_kpi_order_is_canonicalized_before_definition_hashing() -> None:
    first = _rule(declared_kpis=("sales.net_revenue", "inventory.zero_stock_rate"))
    second = _rule(declared_kpis=("inventory.zero_stock_rate", "sales.net_revenue"))

    assert first.declared_kpi_codes == second.declared_kpi_codes
    assert first.definition_hash == second.definition_hash


def test_invalid_runtime_observation_kind_is_rejected() -> None:
    with pytest.raises(DiagnosticEngineValidationError, match="observation kind"):
        replace(_observation("80"), kind=cast(Any, "arbitrary"))


def test_unexpected_domain_defect_becomes_a_closed_internal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_trace(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("sensitive detail must not escape")

    monkeypatch.setattr(engine_module, "_trace_condition", broken_trace)

    result = evaluate_rule(_evaluation())

    assert result.state == "failed"
    assert result.issue is not None
    assert result.issue.code == "internal_evaluation_error"
    assert result.issue.message == "RuntimeError"
    assert "sensitive detail" not in result.canonical_payload()


def test_hash_mismatch_is_reported_as_invalid_rule_snapshot() -> None:
    rule = _rule(condition_hash="0" * 64)

    result = evaluate_rule(_evaluation(rule=rule))

    assert result.state == "failed"
    assert result.issue is not None
    assert result.issue.code == "invalid_rule_snapshot"


def test_contracts_are_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        _evaluation().scope.__setattr__("company_id", COMPANY_ID)


def test_canonicalization_has_a_small_golden_contract() -> None:
    payload = {
        "z": Decimal("1.2300"),
        "a": [UUID("00000000-0000-0000-0000-000000000001"), WINDOW_START],
        "unicode": "farmácia",
    }

    assert canonical_json(payload) == (
        '{"a":["00000000-0000-0000-0000-000000000001",'
        '"2026-07-01T00:00:00.000000Z"],"unicode":"farmácia","z":"1.23"}'
    )
    assert (
        canonical_sha256(payload)
        == "7c0d68aec59cbbbc5bfc0af5995c974d6944353647adb294e8c9da876c22ff6b"
    )


def test_canonicalization_rejects_binary_float_and_non_finite_decimal() -> None:
    with pytest.raises(CanonicalizationError, match="float"):
        canonical_json({"value": 0.1})
    with pytest.raises(CanonicalizationError, match="non-finite"):
        canonical_json({"value": Decimal("NaN")})


def test_engine_module_has_no_infrastructure_or_nondeterministic_calls() -> None:
    module_path = (
        Path(__file__).parents[1] / "src" / "pharma_api" / "domain" / "diagnostics" / "engine.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    calls = {ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}

    assert not any(
        name.startswith(
            ("sqlalchemy", "alembic", "redis", "fastapi", "dramatiq", "pharma_api.infrastructure")
        )
        for name in imported
    )
    assert calls.isdisjoint(
        {
            "datetime.now",
            "datetime.utcnow",
            "time.time",
            "uuid4",
            "random.random",
            "secrets.token_hex",
            "hash",
            "eval",
            "exec",
        }
    )
