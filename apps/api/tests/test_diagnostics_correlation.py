from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from pharma_api.domain.analytics.kpis import KPI_BY_CODE
from pharma_api.domain.diagnostics.actions import ACTION_BY_CODE
from pharma_api.domain.diagnostics.correlation import correlate_diagnostics
from pharma_api.domain.diagnostics.correlation_contracts import (
    MAX_CLUSTER_MEMBERS,
    MAX_CORRELATION_INPUTS,
    MAX_OCCURRENCES_PER_FINGERPRINT,
    CorrelationInput,
    CorrelationPolicyDefinition,
    CorrelationValidationError,
)
from pharma_api.domain.diagnostics.correlation_policies import (
    CORRELATION_POLICY_CATALOG,
    CORRELATION_POLICY_CATALOG_HASH,
)
from pharma_api.domain.diagnostics.engine_contracts import (
    ActionRecommendationCandidate,
    DiagnosticCandidate,
    EvaluationIssue,
    EvaluationResult,
    EvaluationScope,
    EvidenceCandidate,
    HypothesisCandidate,
    canonical_sha256,
)
from pharma_api.domain.diagnostics.rules.catalog import RULE_BY_CODE

TENANT_ID = UUID("10000000-0000-0000-0000-000000000301")
OTHER_TENANT_ID = UUID("10000000-0000-0000-0000-000000000302")
COMPANY_ID = UUID("20000000-0000-0000-0000-000000000301")
OTHER_COMPANY_ID = UUID("20000000-0000-0000-0000-000000000302")
BRANCH_ID = UUID("30000000-0000-0000-0000-000000000301")
OTHER_BRANCH_ID = UUID("30000000-0000-0000-0000-000000000302")
WINDOW_START = datetime(2026, 7, 8, tzinfo=UTC)
WINDOW_END = datetime(2026, 7, 14, 23, 59, 59, tzinfo=UTC)
EVALUATED_AT = datetime(2026, 7, 15, 8, tzinfo=UTC)
BRANCH_SCOPE = EvaluationScope(TENANT_ID, "branch", COMPANY_ID, BRANCH_ID)


def _fingerprint(token: str) -> str:
    return canonical_sha256({"test_fingerprint": token})


def _rehash(result: EvaluationResult) -> EvaluationResult:
    return replace(
        result,
        result_hash=canonical_sha256(result.as_dict(include_result_hash=False)),
    )


def _evidence(code: str, kpi_code: str, marker: str = "base") -> EvidenceCandidate:
    payload = {
        "evidence_code": f"{code}_signal",
        "evidence_type": "comparison",
        "kpi_code": kpi_code,
        "observed_value": Decimal("90"),
        "reference_value": Decimal("100"),
        "unit": KPI_BY_CODE[kpi_code].unit,
        "period_start": WINDOW_START,
        "period_end": WINDOW_END,
        "direction": "below",
        "source_type": "analytics_kpi",
        "analytics_data_version": 31,
        "formula_version": 1,
        "detail": f"Observed governed signal {marker}.",
        "relation": "supports",
        "weight": Decimal("1"),
        "lineage_ref": f"lineage://correlation/{marker}",
        "stable_order": 0,
    }
    return EvidenceCandidate(
        **cast(Any, payload),
        evidence_hash=canonical_sha256(payload),
    )


def _matched_result(
    code: str = "sales.net_revenue_decline",
    *,
    fingerprint: str | None = None,
    evaluated_at: datetime = EVALUATED_AT,
    severity: str | None = None,
    priority: int | None = None,
    confidence: Decimal = Decimal("0.9000"),
    evidence: tuple[EvidenceCandidate, ...] | None = None,
    hypothesis_status: str = "supported",
) -> EvaluationResult:
    rule = RULE_BY_CODE[code]
    action_reference = rule.actions[0]
    action = ACTION_BY_CODE[action_reference.action_code]
    diagnostic = DiagnosticCandidate(
        diagnostic_code=rule.code,
        fingerprint=fingerprint or _fingerprint(code),
        domain=rule.domain,
        title=rule.title,
        summary=rule.summary,
        severity=cast(Any, severity or rule.base_severity),
        confidence_score=confidence,
        priority=priority or action.default_priority,
        detected_at=evaluated_at,
        affected_from=WINDOW_START,
        affected_to=WINDOW_END,
        primary_kpi_code=rule.primary_kpi_code,
        observed_value=Decimal("90"),
        reference_value=Decimal("100"),
        value_unit=KPI_BY_CODE[rule.primary_kpi_code].unit,
        analytics_data_version=31,
        formula_version=1,
    )
    actual_evidence = evidence or (_evidence(code, rule.primary_kpi_code),)
    hypothesis_definition = rule.hypotheses[0]
    hypothesis = HypothesisCandidate(
        hypothesis_code=hypothesis_definition.hypothesis_code,
        evaluation_status=cast(Any, hypothesis_status),
        confidence_score=confidence,
        rank=1,
        supporting_evidence_codes=(actual_evidence[0].evidence_code,),
        contradicting_evidence_codes=(),
        explanation=hypothesis_definition.explanation,
        logic_version=hypothesis_definition.logic_version,
        evaluated_at=evaluated_at,
    )
    recommendation = ActionRecommendationCandidate(
        action_code=action.code,
        action_version=action.version,
        title=action.title,
        suggested_priority=action.default_priority,
        stable_order=0,
        rationale=action_reference.rationale,
        action_definition_hash=canonical_sha256(action.as_dict()),
    )
    return _rehash(
        EvaluationResult(
            state="matched",
            rule_definition_id=rule.rule_definition_id,
            rule_version_number=rule.version,
            engine_version="2d-cp2-b3a.1",
            evaluated_at=evaluated_at,
            dependencies=(rule.primary_kpi_code,),
            observations=(),
            trace=(),
            diagnostic=diagnostic,
            evidence=actual_evidence,
            hypotheses=(hypothesis,),
            recommendations=(recommendation,),
        )
    )


def _nonmatched_result(state: str) -> EvaluationResult:
    rule = RULE_BY_CODE["sales.net_revenue_decline"]
    issue = (
        None
        if state == "not_matched"
        else EvaluationIssue(
            code=cast(
                Any,
                "condition_not_evaluable" if state == "skipped" else "internal_evaluation_error",
            ),
            message=f"deterministic {state} test result",
        )
    )
    return _rehash(
        EvaluationResult(
            state=cast(Any, state),
            rule_definition_id=rule.rule_definition_id,
            rule_version_number=rule.version,
            engine_version="2d-cp2-b3a.1",
            evaluated_at=EVALUATED_AT,
            dependencies=(rule.primary_kpi_code,),
            observations=(),
            trace=(),
            issue=issue,
        )
    )


def _input(result: EvaluationResult, scope: EvaluationScope = BRANCH_SCOPE) -> CorrelationInput:
    return CorrelationInput(scope=scope, result=result)


def test_empty_batch_is_canonical_and_has_zero_metrics() -> None:
    result = correlate_diagnostics(())
    assert result.diagnostics == ()
    assert result.clusters == ()
    assert result.metrics.total_inputs == 0
    assert result.metrics.accepted_occurrences == 0
    assert result.policy_catalog_hash == CORRELATION_POLICY_CATALOG_HASH
    assert len(result.batch_hash) == 64


@pytest.mark.parametrize("state", ["not_matched", "skipped", "failed"])
def test_nonmatched_states_only_contribute_to_immutable_metrics(state: str) -> None:
    result = correlate_diagnostics((_input(_nonmatched_result(state)),))
    assert result.diagnostics == ()
    assert result.clusters == ()
    assert getattr(result.metrics, f"{state}_inputs") == 1
    assert result.metrics.accepted_occurrences == 0


def test_matched_without_diagnostic_fails_closed() -> None:
    invalid = _rehash(replace(_matched_result(), diagnostic=None))
    with pytest.raises(CorrelationValidationError, match="missing its diagnostic"):
        correlate_diagnostics((_input(invalid),))


@pytest.mark.parametrize("field", ["fingerprint", "result_hash"])
def test_invalid_sha256_contracts_fail_closed(field: str) -> None:
    source = _matched_result()
    if field == "fingerprint":
        assert source.diagnostic is not None
        source = _rehash(replace(source, diagnostic=replace(source.diagnostic, fingerprint="bad")))
    else:
        source = replace(source, result_hash="bad")
    with pytest.raises(CorrelationValidationError, match=field):
        correlate_diagnostics((_input(source),))


def test_same_fingerprint_and_scope_deduplicates_to_two_occurrences() -> None:
    first = _matched_result(fingerprint=_fingerprint("same"))
    second_time = EVALUATED_AT + timedelta(hours=1)
    assert first.diagnostic is not None
    second = _rehash(
        replace(
            first,
            evaluated_at=second_time,
            diagnostic=replace(first.diagnostic, detected_at=second_time),
            hypotheses=(replace(first.hypotheses[0], evaluated_at=second_time),),
        )
    )
    batch = correlate_diagnostics((_input(first), _input(second)))
    diagnostic = batch.diagnostics[0]
    assert len(batch.diagnostics) == 1
    assert diagnostic.occurrence_count == 2
    assert diagnostic.first_observed_at == EVALUATED_AT
    assert diagnostic.last_observed_at == second_time
    assert diagnostic.result_hashes == tuple(sorted((first.result_hash, second.result_hash)))
    assert len(diagnostic.provenance) == 2


@pytest.mark.parametrize(
    "scope",
    [
        EvaluationScope(OTHER_TENANT_ID, "branch", COMPANY_ID, BRANCH_ID),
        EvaluationScope(TENANT_ID, "company", OTHER_COMPANY_ID),
        EvaluationScope(TENANT_ID, "branch", COMPANY_ID, OTHER_BRANCH_ID),
        EvaluationScope(TENANT_ID, "company", COMPANY_ID),
    ],
    ids=["tenant", "company", "branch", "scope-level"],
)
def test_same_fingerprint_never_deduplicates_across_scope_identity(scope: EvaluationScope) -> None:
    fingerprint = _fingerprint("cross-scope")
    batch = correlate_diagnostics(
        (
            _input(_matched_result(fingerprint=fingerprint), BRANCH_SCOPE),
            _input(_matched_result(fingerprint=fingerprint), scope),
        )
    )
    assert len(batch.diagnostics) == 2
    assert all(item.occurrence_count == 1 for item in batch.diagnostics)


def test_same_fingerprint_with_incompatible_code_fails_closed() -> None:
    fingerprint = _fingerprint("conflict")
    first = _matched_result("sales.net_revenue_decline", fingerprint=fingerprint)
    second = _matched_result("sales.net_revenue_below_network", fingerprint=fingerprint)
    with pytest.raises(CorrelationValidationError, match="incompatible immutable identities"):
        correlate_diagnostics((_input(first), _input(second)))


def test_severity_priority_and_confidence_aggregation_never_weakens_signal() -> None:
    fingerprint = _fingerprint("aggregate")
    weak = _matched_result(
        fingerprint=fingerprint,
        severity="medium",
        priority=3,
        confidence=Decimal("0.6000"),
    )
    strong = _matched_result(
        fingerprint=fingerprint,
        evaluated_at=EVALUATED_AT + timedelta(hours=1),
        severity="critical",
        priority=1,
        confidence=Decimal("0.9500"),
    )
    diagnostic = correlate_diagnostics((_input(weak), _input(strong))).diagnostics[0]
    assert diagnostic.severity == "critical"
    assert diagnostic.priority == 1
    assert diagnostic.confidence_score == Decimal("0.9500")
    assert diagnostic.representative_result_hash == strong.result_hash


def test_repeated_evidence_is_deduplicated_by_evidence_hash() -> None:
    fingerprint = _fingerprint("evidence")
    first = _matched_result(fingerprint=fingerprint)
    second = _matched_result(fingerprint=fingerprint)
    diagnostic = correlate_diagnostics((_input(first), _input(second))).diagnostics[0]
    assert len(diagnostic.evidence) == 1


def test_logical_evidence_hash_collision_is_rejected() -> None:
    first = _matched_result(fingerprint=_fingerprint("evidence-collision"))
    original = first.evidence[0]
    invalid = replace(original, detail="Different content under the same evidence hash.")
    second = _matched_result(fingerprint=_fingerprint("evidence-collision"), evidence=(invalid,))
    with pytest.raises(CorrelationValidationError, match="invalid canonical hash"):
        correlate_diagnostics((_input(first), _input(second)))


def test_repeated_hypotheses_are_one_identity_with_distinct_assessment_times() -> None:
    fingerprint = _fingerprint("hypothesis")
    first = _matched_result(fingerprint=fingerprint)
    later = EVALUATED_AT + timedelta(hours=1)
    assert first.diagnostic is not None
    second = _rehash(
        replace(
            first,
            evaluated_at=later,
            diagnostic=replace(first.diagnostic, detected_at=later),
            hypotheses=(replace(first.hypotheses[0], evaluated_at=later),),
        )
    )
    hypothesis = correlate_diagnostics((_input(first), _input(second))).diagnostics[0].hypotheses[0]
    assert tuple(item.evaluation_status for item in hypothesis.assessments) == (
        "supported",
        "supported",
    )
    assert tuple(item.evaluated_at for item in hypothesis.assessments) == (EVALUATED_AT, later)


def test_contradictory_hypothesis_assessments_are_preserved_not_promoted_to_fact() -> None:
    fingerprint = _fingerprint("hypothesis-status")
    first = _matched_result(fingerprint=fingerprint, hypothesis_status="supported")
    later = EVALUATED_AT + timedelta(hours=1)
    assert first.diagnostic is not None
    contradicted = replace(
        first.hypotheses[0],
        evaluation_status="contradicted",
        evaluated_at=later,
    )
    second = _rehash(
        replace(
            first,
            evaluated_at=later,
            diagnostic=replace(first.diagnostic, detected_at=later),
            hypotheses=(contradicted,),
        )
    )
    hypothesis = correlate_diagnostics((_input(first), _input(second))).diagnostics[0].hypotheses[0]
    assert tuple(item.evaluation_status for item in hypothesis.assessments) == (
        "supported",
        "contradicted",
    )


def test_conflicting_hypothesis_at_same_instant_fails_closed() -> None:
    fingerprint = _fingerprint("hypothesis-conflict")
    first = _matched_result(fingerprint=fingerprint)
    conflicting = replace(first.hypotheses[0], evaluation_status="contradicted")
    second = _rehash(replace(first, hypotheses=(conflicting,)))
    with pytest.raises(CorrelationValidationError, match="conflicting assessments"):
        correlate_diagnostics((_input(first), _input(second)))


def test_recommendations_are_deduplicated_by_governed_identity() -> None:
    fingerprint = _fingerprint("recommendation")
    first = _matched_result(fingerprint=fingerprint)
    second = _matched_result(fingerprint=fingerprint)
    recommendations = (
        correlate_diagnostics((_input(first), _input(second))).diagnostics[0].recommendations
    )
    assert len(recommendations) == 1
    assert recommendations[0].execution_mode == "human_review_required"
    assert recommendations[0].requires_human_review is True
    assert recommendations[0].allows_automatic_financial_execution is False


def test_recommendation_guardrail_violation_blocks_entire_batch() -> None:
    source = _matched_result()
    invalid_recommendation = replace(
        source.recommendations[0],
        allows_automatic_financial_execution=cast(Any, True),
    )
    invalid = _rehash(replace(source, recommendations=(invalid_recommendation,)))
    with pytest.raises(CorrelationValidationError, match="advisory-only guardrails"):
        correlate_diagnostics((_input(invalid),))


def test_input_order_reversal_is_byte_for_byte_deterministic() -> None:
    first = _matched_result("sales.net_revenue_decline")
    second = _matched_result("sales.net_revenue_below_network")
    forward = correlate_diagnostics((_input(first), _input(second)))
    reverse = correlate_diagnostics((_input(second), _input(first)))
    assert forward == reverse
    assert forward.canonical_payload() == reverse.canonical_payload()


def test_all_permutations_of_small_batch_are_identical() -> None:
    duplicate_fingerprint = _fingerprint("permutation-duplicate")
    values = (
        _input(_matched_result("sales.net_revenue_decline", fingerprint=duplicate_fingerprint)),
        _input(_matched_result("sales.net_revenue_decline", fingerprint=duplicate_fingerprint)),
        _input(_matched_result("sales.net_revenue_below_network")),
    )
    payloads = {
        correlate_diagnostics(permutation).canonical_payload()
        for permutation in itertools.permutations(values)
    }
    assert len(payloads) == 1


def test_policy_order_does_not_change_output() -> None:
    values = (
        _input(_matched_result("sales.net_revenue_decline")),
        _input(_matched_result("sales.net_revenue_below_network")),
    )
    forward = correlate_diagnostics(values, policies=CORRELATION_POLICY_CATALOG)
    reverse = correlate_diagnostics(values, policies=tuple(reversed(CORRELATION_POLICY_CATALOG)))
    assert forward.canonical_payload() == reverse.canonical_payload()


def test_explicit_policy_groups_distinct_fingerprints_in_compatible_scope_and_period() -> None:
    first = _matched_result("sales.net_revenue_decline")
    second = _matched_result("sales.net_revenue_below_network")
    batch = correlate_diagnostics((_input(first), _input(second)))
    assert len(batch.diagnostics) == 2
    assert len(batch.clusters) == 1
    cluster = batch.clusters[0]
    assert cluster.policy_code == "correlation.sales_net_revenue"
    assert cluster.member_fingerprints == tuple(
        sorted((cast(Any, first.diagnostic).fingerprint, cast(Any, second.diagnostic).fingerprint))
    )
    assert len(cluster.cluster_fingerprint) == 64
    assert cluster.trace[0].member_fingerprints == cluster.member_fingerprints


def test_distinct_fingerprints_without_policy_remain_two_singleton_groups() -> None:
    values = (
        _input(_matched_result("sales.net_revenue_decline")),
        _input(_matched_result("sales.net_revenue_below_network")),
    )
    batch = correlate_diagnostics(values, policies=())
    assert len(batch.clusters) == 2
    assert {cluster.policy_code for cluster in batch.clusters} == {"correlation.singleton"}


def test_explicit_policy_does_not_group_incompatible_periods() -> None:
    first = _matched_result("sales.net_revenue_decline")
    second = _matched_result("sales.net_revenue_below_network")
    assert second.diagnostic is not None
    shifted = _rehash(
        replace(
            second,
            diagnostic=replace(
                second.diagnostic,
                affected_from=WINDOW_START + timedelta(days=1),
                affected_to=WINDOW_END + timedelta(days=1),
            ),
        )
    )
    batch = correlate_diagnostics((_input(first), _input(shifted)))
    assert len(batch.clusters) == 2
    assert all(cluster.policy_code == "correlation.singleton" for cluster in batch.clusters)


def test_explicit_policy_does_not_group_incompatible_scopes() -> None:
    other_scope = EvaluationScope(TENANT_ID, "branch", COMPANY_ID, OTHER_BRANCH_ID)
    batch = correlate_diagnostics(
        (
            _input(_matched_result("sales.net_revenue_decline")),
            _input(_matched_result("sales.net_revenue_below_network"), other_scope),
        )
    )
    assert len(batch.clusters) == 2


def test_primary_diagnostic_selection_uses_documented_total_tiebreak() -> None:
    weak = _matched_result(
        "sales.net_revenue_decline",
        severity="medium",
        priority=3,
        confidence=Decimal("0.8000"),
    )
    strong = _matched_result(
        "sales.net_revenue_below_network",
        severity="critical",
        priority=1,
        confidence=Decimal("0.9500"),
    )
    assert strong.diagnostic is not None
    cluster = correlate_diagnostics((_input(weak), _input(strong))).clusters[0]
    assert cluster.primary_diagnostic_fingerprint == strong.diagnostic.fingerprint
    assert cluster.aggregate_severity == "critical"
    assert cluster.priority == 1


def test_group_fingerprint_is_independent_of_input_order() -> None:
    first = _input(_matched_result("sales.net_revenue_decline"))
    second = _input(_matched_result("sales.net_revenue_below_network"))
    a = correlate_diagnostics((first, second)).clusters[0]
    b = correlate_diagnostics((second, first)).clusters[0]
    assert a.cluster_fingerprint == b.cluster_fingerprint


def test_batch_limit_fails_before_partial_output() -> None:
    value = _input(_nonmatched_result("not_matched"))
    with pytest.raises(CorrelationValidationError, match="batch input limit"):
        correlate_diagnostics((value,) * (MAX_CORRELATION_INPUTS + 1))


def test_batch_limit_does_not_exhaust_an_unbounded_iterable() -> None:
    value = _input(_nonmatched_result("not_matched"))
    consumed = 0

    def values() -> Iterator[CorrelationInput]:
        nonlocal consumed
        while True:
            consumed += 1
            yield value

    with pytest.raises(CorrelationValidationError, match="batch input limit"):
        correlate_diagnostics(values())
    assert consumed == MAX_CORRELATION_INPUTS + 1


def test_occurrence_limit_is_enforced_per_exact_identity() -> None:
    value = _input(_matched_result(fingerprint=_fingerprint("occurrence-limit")))
    with pytest.raises(CorrelationValidationError, match="occurrence limit"):
        correlate_diagnostics((value,) * (MAX_OCCURRENCES_PER_FINGERPRINT + 1))


def test_runtime_cluster_member_limit_is_enforced() -> None:
    policy = next(
        item for item in CORRELATION_POLICY_CATALOG if item.code == "correlation.sales_net_revenue"
    )
    values = tuple(
        _input(
            _matched_result(
                (
                    "sales.net_revenue_decline"
                    if index % 2 == 0
                    else "sales.net_revenue_below_network"
                ),
                fingerprint=_fingerprint(f"cluster-limit-{index}"),
            )
        )
        for index in range(MAX_CLUSTER_MEMBERS + 1)
    )
    with pytest.raises(CorrelationValidationError, match="group member limit"):
        correlate_diagnostics(values, policies=(policy,))


def test_outputs_are_frozen_and_deeply_tuple_based() -> None:
    result = correlate_diagnostics((_input(_matched_result()),))
    with pytest.raises(FrozenInstanceError):
        result.batch_hash = "0" * 64  # type: ignore[misc]
    assert isinstance(result.diagnostics, tuple)
    assert isinstance(result.clusters, tuple)
    assert isinstance(result.diagnostics[0].evidence, tuple)
    assert isinstance(result.diagnostics[0].hypotheses, tuple)
    assert isinstance(result.diagnostics[0].recommendations, tuple)


def test_canonical_serialization_recomputes_batch_hash() -> None:
    result = correlate_diagnostics((_input(_matched_result()),))
    assert result.batch_hash == canonical_sha256(result.as_dict(include_batch_hash=False))
    assert json.loads(result.canonical_payload())["batch_hash"] == result.batch_hash


def test_process_determinism_under_two_pythonhashseeds() -> None:
    root = Path(__file__).parents[1]
    script = """
from pharma_api.domain.diagnostics.correlation import correlate_diagnostics
from pharma_api.domain.diagnostics.correlation_policies import CORRELATION_MANIFEST_HASH
result = correlate_diagnostics(())
print(result.batch_hash)
print(result.policy_catalog_hash)
print(CORRELATION_MANIFEST_HASH)
"""
    outputs = []
    for seed in ("1", "987654"):
        environment = dict(os.environ)
        environment["PYTHONHASHSEED"] = seed
        environment["PYTHONPATH"] = str(root / "src")
        outputs.append(
            # Test-only subprocess using sys.executable, fixed arguments,
            # shell=False and no user-controlled input.
            subprocess.check_output(  # noqa: S603
                [sys.executable, "-c", script],
                cwd=root,
                env=environment,
                shell=False,
                text=True,
            )
        )
    assert outputs[0] == outputs[1]


def test_policy_definition_cannot_be_mutated_after_creation() -> None:
    policy: CorrelationPolicyDefinition = CORRELATION_POLICY_CATALOG[0]
    with pytest.raises(FrozenInstanceError):
        policy.status = "inactive"  # type: ignore[misc]


def test_representative_contract_batch_hash_is_golden() -> None:
    fingerprint = _fingerprint("golden-dedup")
    batch = correlate_diagnostics(
        (
            _input(_matched_result("sales.net_revenue_decline", fingerprint=fingerprint)),
            _input(_matched_result("sales.net_revenue_decline", fingerprint=fingerprint)),
            _input(_matched_result("sales.net_revenue_below_network")),
        )
    )
    assert batch.batch_hash == "7768a2215d5750435bf0b60ab6e11c8e18308994070533c4044a0df80d85fdc3"
