"""Pure deterministic deduplication and governed correlation of diagnostic results."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import replace
from decimal import Decimal
from itertools import islice

from pharma_api.domain.diagnostics.correlation_contracts import (
    MAX_CLUSTER_MEMBERS,
    MAX_CORRELATED_EVIDENCE,
    MAX_CORRELATED_HYPOTHESES,
    MAX_CORRELATED_RECOMMENDATIONS,
    MAX_CORRELATION_INPUTS,
    MAX_OCCURRENCES_PER_FINGERPRINT,
    CorrelatedHypothesis,
    CorrelatedRecommendation,
    CorrelationBatchMetrics,
    CorrelationBatchResult,
    CorrelationInput,
    CorrelationPolicyDefinition,
    CorrelationTraceEntry,
    CorrelationValidationError,
    DeduplicatedDiagnosticCandidate,
    DiagnosticClusterCandidate,
    OccurrenceProvenance,
    RuleOrigin,
    recommendation_identity,
)
from pharma_api.domain.diagnostics.correlation_policies import (
    CORRELATION_POLICY_CATALOG,
    validate_correlation_policy_catalog,
)
from pharma_api.domain.diagnostics.engine_contracts import (
    _SEVERITY_RANK,
    SHA256_PATTERN,
    STABLE_CODE_PATTERN,
    ActionRecommendationCandidate,
    EvaluationResult,
    EvaluationScope,
    EvidenceCandidate,
    HypothesisCandidate,
    canonical_json,
    canonical_sha256,
)
from pharma_api.domain.diagnostics.rules.catalog import RULE_BY_CODE

_SINGLETON_POLICY_CODE = "correlation.singleton"
_SINGLETON_POLICY_VERSION = 1
_SINGLETON_POLICY_REASON = "No governed multi-diagnostic correlation policy matched this candidate."
_SINGLETON_POLICY_HASH = canonical_sha256(
    {
        "code": _SINGLETON_POLICY_CODE,
        "version": _SINGLETON_POLICY_VERSION,
        "reason": _SINGLETON_POLICY_REASON,
    }
)


def _scope_key(scope: EvaluationScope) -> tuple[str, str, str, str]:
    return (
        str(scope.tenant_id),
        scope.scope_type,
        "" if scope.company_id is None else str(scope.company_id),
        "" if scope.branch_id is None else str(scope.branch_id),
    )


def _identity_key(item: CorrelationInput) -> tuple[str, str, str, str, str]:
    diagnostic = item.result.diagnostic
    if diagnostic is None:
        raise CorrelationValidationError("matched result is missing its diagnostic candidate")
    return (*_scope_key(item.scope), diagnostic.fingerprint)


def _require_sha256(value: str, field: str) -> None:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise CorrelationValidationError(f"{field} must be a lowercase SHA-256 digest")


def _validate_evidence(item: EvidenceCandidate) -> None:
    _require_sha256(item.evidence_hash, "evidence_hash")
    payload = item.as_dict()
    payload.pop("evidence_hash")
    if canonical_sha256(payload) != item.evidence_hash:
        raise CorrelationValidationError(
            f"evidence {item.evidence_code} has an invalid canonical hash"
        )


def _validate_hypothesis(item: HypothesisCandidate) -> None:
    if STABLE_CODE_PATTERN.fullmatch(item.hypothesis_code) is None:
        raise CorrelationValidationError("hypothesis_code is not stable")
    if not item.logic_version or item.logic_version != item.logic_version.strip():
        raise CorrelationValidationError("hypothesis logic_version must be trimmed")
    if item.confidence_score is not None and not Decimal("0") <= item.confidence_score <= 1:
        raise CorrelationValidationError("hypothesis confidence must be between 0 and 1")
    if item.rank < 1:
        raise CorrelationValidationError("hypothesis rank must be >= 1")
    if item.evaluation_status == "not_evaluated" and item.evaluated_at is not None:
        raise CorrelationValidationError("not_evaluated hypothesis cannot have evaluated_at")
    if item.evaluation_status != "not_evaluated" and item.evaluated_at is None:
        raise CorrelationValidationError("evaluated hypothesis requires evaluated_at")


def _validate_recommendation(item: ActionRecommendationCandidate) -> None:
    _require_sha256(item.action_definition_hash, "action_definition_hash")
    if (
        item.execution_mode != "human_review_required"
        or item.requires_human_review is not True
        or item.allows_automatic_financial_execution is not False
    ):
        raise CorrelationValidationError(
            f"recommendation {item.action_code} violates advisory-only guardrails"
        )
    if not 1 <= item.suggested_priority <= 4:
        raise CorrelationValidationError("recommendation priority must be between 1 and 4")


def _validate_result(item: CorrelationInput) -> bool:
    result = item.result
    _require_sha256(result.result_hash, "result_hash")
    if canonical_sha256(result.as_dict(include_result_hash=False)) != result.result_hash:
        raise CorrelationValidationError("result_hash does not match the canonical result payload")
    if result.state != "matched":
        if (
            result.diagnostic is not None
            or result.evidence
            or result.hypotheses
            or result.recommendations
        ):
            raise CorrelationValidationError(
                f"{result.state} result cannot carry diagnostic candidates"
            )
        return False
    diagnostic = result.diagnostic
    if diagnostic is None:
        raise CorrelationValidationError("matched result is missing its diagnostic candidate")
    _require_sha256(diagnostic.fingerprint, "fingerprint")
    if STABLE_CODE_PATTERN.fullmatch(diagnostic.diagnostic_code) is None:
        raise CorrelationValidationError("diagnostic_code is not stable")
    rule = RULE_BY_CODE.get(diagnostic.diagnostic_code)
    if rule is None:
        raise CorrelationValidationError(
            f"diagnostic {diagnostic.diagnostic_code} is not in the governed rule catalog"
        )
    if (
        result.rule_definition_id != rule.rule_definition_id
        or result.rule_version_number != rule.version
        or diagnostic.domain != rule.domain
        or diagnostic.primary_kpi_code != rule.primary_kpi_code
    ):
        raise CorrelationValidationError(
            f"diagnostic {diagnostic.diagnostic_code} is incompatible with its governed rule"
        )
    if diagnostic.affected_to < diagnostic.affected_from:
        raise CorrelationValidationError("diagnostic affected period is inverted")
    if not Decimal("0") <= diagnostic.confidence_score <= 1:
        raise CorrelationValidationError("diagnostic confidence must be between 0 and 1")
    if not 1 <= diagnostic.priority <= 4:
        raise CorrelationValidationError("diagnostic priority must be between 1 and 4")
    if len(result.evidence) > MAX_CORRELATED_EVIDENCE:
        raise CorrelationValidationError("result evidence limit exceeded")
    if len(result.hypotheses) > MAX_CORRELATED_HYPOTHESES:
        raise CorrelationValidationError("result hypothesis limit exceeded")
    if len(result.recommendations) > MAX_CORRELATED_RECOMMENDATIONS:
        raise CorrelationValidationError("result recommendation limit exceeded")
    for evidence in result.evidence:
        _validate_evidence(evidence)
    for hypothesis in result.hypotheses:
        _validate_hypothesis(hypothesis)
    for recommendation in result.recommendations:
        _validate_recommendation(recommendation)
    return True


def _compatibility_signature(result: EvaluationResult) -> tuple[object, ...]:
    diagnostic = result.diagnostic
    if diagnostic is None:
        raise CorrelationValidationError("matched result is missing its diagnostic candidate")
    return (
        diagnostic.diagnostic_code,
        diagnostic.domain,
        diagnostic.title,
        diagnostic.summary,
        diagnostic.primary_kpi_code,
        diagnostic.value_unit,
        diagnostic.observed_value,
        diagnostic.reference_value,
        diagnostic.analytics_data_version,
        diagnostic.formula_version,
        diagnostic.affected_from,
        diagnostic.affected_to,
        result.rule_definition_id,
        result.rule_version_number,
    )


def _select_representative(items: tuple[CorrelationInput, ...]) -> CorrelationInput:
    remaining = list(items)
    highest_severity = max(
        _SEVERITY_RANK[item.result.diagnostic.severity]
        for item in remaining
        if item.result.diagnostic is not None
    )
    remaining = [
        item
        for item in remaining
        if item.result.diagnostic is not None
        and _SEVERITY_RANK[item.result.diagnostic.severity] == highest_severity
    ]
    most_urgent = min(
        item.result.diagnostic.priority for item in remaining if item.result.diagnostic is not None
    )
    remaining = [
        item
        for item in remaining
        if item.result.diagnostic is not None and item.result.diagnostic.priority == most_urgent
    ]
    highest_confidence = max(
        item.result.diagnostic.confidence_score
        for item in remaining
        if item.result.diagnostic is not None
    )
    remaining = [
        item
        for item in remaining
        if item.result.diagnostic is not None
        and item.result.diagnostic.confidence_score == highest_confidence
    ]
    latest_period = max(
        item.result.diagnostic.affected_to
        for item in remaining
        if item.result.diagnostic is not None
    )
    remaining = [
        item
        for item in remaining
        if item.result.diagnostic is not None
        and item.result.diagnostic.affected_to == latest_period
    ]
    return min(
        remaining,
        key=lambda item: (
            item.result.diagnostic.diagnostic_code if item.result.diagnostic else "",
            str(item.result.rule_definition_id),
            item.result.result_hash,
        ),
    )


def _merge_evidence(items: tuple[CorrelationInput, ...]) -> tuple[EvidenceCandidate, ...]:
    by_hash: dict[str, EvidenceCandidate] = {}
    canonical_by_hash: dict[str, str] = {}
    for item in items:
        for evidence in item.result.evidence:
            document = canonical_json(evidence.as_dict())
            previous = canonical_by_hash.setdefault(evidence.evidence_hash, document)
            if previous != document:
                raise CorrelationValidationError(
                    f"evidence hash collision for {evidence.evidence_hash}"
                )
            by_hash.setdefault(evidence.evidence_hash, evidence)
    if len(by_hash) > MAX_CORRELATED_EVIDENCE:
        raise CorrelationValidationError("deduplicated evidence limit exceeded")
    return tuple(
        sorted(by_hash.values(), key=lambda value: (value.stable_order, value.evidence_hash))
    )


def _merge_hypotheses(items: tuple[CorrelationInput, ...]) -> tuple[CorrelatedHypothesis, ...]:
    grouped: dict[tuple[str, str], list[HypothesisCandidate]] = defaultdict(list)
    assessment_documents: dict[tuple[str, str, str], str] = {}
    for item in items:
        for hypothesis in item.result.hypotheses:
            evaluated_key = (
                "" if hypothesis.evaluated_at is None else hypothesis.evaluated_at.isoformat()
            )
            collision_key = (
                hypothesis.hypothesis_code,
                hypothesis.logic_version,
                evaluated_key,
            )
            document = canonical_json(hypothesis.as_dict())
            previous = assessment_documents.setdefault(collision_key, document)
            if previous != document:
                raise CorrelationValidationError(
                    "hypothesis identity has conflicting assessments at the same instant"
                )
            grouped[(hypothesis.hypothesis_code, hypothesis.logic_version)].append(hypothesis)
    if len(grouped) > MAX_CORRELATED_HYPOTHESES:
        raise CorrelationValidationError("deduplicated hypothesis limit exceeded")
    merged: list[CorrelatedHypothesis] = []
    for (code, logic_version), values in sorted(grouped.items()):
        unique_assessments = {canonical_json(item.as_dict()): item for item in values}
        merged.append(
            CorrelatedHypothesis(
                hypothesis_code=code,
                logic_version=logic_version,
                assessments=tuple(
                    unique_assessments[document] for document in sorted(unique_assessments)
                ),
            )
        )
    return tuple(merged)


def _merge_recommendations(
    items: tuple[CorrelationInput, ...],
) -> tuple[CorrelatedRecommendation, ...]:
    grouped: dict[tuple[str, int, str], list[ActionRecommendationCandidate]] = defaultdict(list)
    definition_hashes: dict[tuple[str, int], str] = {}
    for item in items:
        for recommendation in item.result.recommendations:
            version_key = recommendation.action_code, recommendation.action_version
            previous_hash = definition_hashes.setdefault(
                version_key, recommendation.action_definition_hash
            )
            if previous_hash != recommendation.action_definition_hash:
                raise CorrelationValidationError(
                    f"action definition conflict for {recommendation.action_code}"
                )
            grouped[recommendation_identity(recommendation)].append(recommendation)
    if len(grouped) > MAX_CORRELATED_RECOMMENDATIONS:
        raise CorrelationValidationError("deduplicated recommendation limit exceeded")
    merged: list[CorrelatedRecommendation] = []
    for identity, values in sorted(grouped.items()):
        titles = {item.title for item in values}
        if len(titles) != 1:
            raise CorrelationValidationError(
                f"action title conflict for {identity[0]} version {identity[1]}"
            )
        merged.append(
            CorrelatedRecommendation(
                action_code=identity[0],
                action_version=identity[1],
                action_definition_hash=identity[2],
                title=next(iter(titles)),
                suggested_priority=min(item.suggested_priority for item in values),
                stable_orders=tuple(sorted({item.stable_order for item in values})),
                rationales=tuple(sorted({item.rationale for item in values})),
            )
        )
    return tuple(
        sorted(
            merged,
            key=lambda item: (
                item.suggested_priority,
                item.action_code,
                item.action_version,
                item.action_definition_hash,
            ),
        )
    )


def _deduplicate_group(
    identity: tuple[str, str, str, str, str],
    items: tuple[CorrelationInput, ...],
) -> DeduplicatedDiagnosticCandidate:
    if len(items) > MAX_OCCURRENCES_PER_FINGERPRINT:
        raise CorrelationValidationError(
            f"occurrence limit exceeded for fingerprint {identity[-1]}"
        )
    signatures = {_compatibility_signature(item.result) for item in items}
    if len(signatures) != 1:
        raise CorrelationValidationError(
            f"fingerprint {identity[-1]} is associated with incompatible immutable identities"
        )
    representative = _select_representative(items)
    diagnostic = representative.result.diagnostic
    if diagnostic is None:
        raise CorrelationValidationError("matched result is missing its diagnostic candidate")
    origins = tuple(
        sorted(
            {
                RuleOrigin(item.result.rule_definition_id, item.result.rule_version_number)
                for item in items
            },
            key=lambda origin: (str(origin.rule_definition_id), origin.rule_version_number),
        )
    )
    provenance = tuple(
        sorted(
            (
                OccurrenceProvenance(
                    result_hash=item.result.result_hash,
                    rule_origin=RuleOrigin(
                        item.result.rule_definition_id,
                        item.result.rule_version_number,
                    ),
                    evaluated_at=item.result.evaluated_at,
                    affected_from=item.result.diagnostic.affected_from,
                    affected_to=item.result.diagnostic.affected_to,
                )
                for item in items
                if item.result.diagnostic is not None
            ),
            key=lambda value: (
                value.evaluated_at,
                value.result_hash,
            ),
        )
    )
    severities = [
        item.result.diagnostic.severity for item in items if item.result.diagnostic is not None
    ]
    aggregate_severity = max(severities, key=lambda value: _SEVERITY_RANK[value])
    priorities = [
        item.result.diagnostic.priority for item in items if item.result.diagnostic is not None
    ]
    confidences = [
        item.result.diagnostic.confidence_score
        for item in items
        if item.result.diagnostic is not None
    ]
    affected_from = min(
        item.result.diagnostic.affected_from for item in items if item.result.diagnostic is not None
    )
    affected_to = max(
        item.result.diagnostic.affected_to for item in items if item.result.diagnostic is not None
    )
    first_observed_at = min(
        item.result.diagnostic.detected_at for item in items if item.result.diagnostic is not None
    )
    last_observed_at = max(
        item.result.diagnostic.detected_at for item in items if item.result.diagnostic is not None
    )
    return DeduplicatedDiagnosticCandidate(
        scope=representative.scope,
        fingerprint=diagnostic.fingerprint,
        diagnostic_code=diagnostic.diagnostic_code,
        domain=diagnostic.domain,
        title=diagnostic.title,
        summary=diagnostic.summary,
        severity=aggregate_severity,
        priority=min(priorities),
        confidence_score=max(confidences),
        primary_kpi_code=diagnostic.primary_kpi_code,
        value_unit=diagnostic.value_unit,
        observed_value=diagnostic.observed_value,
        reference_value=diagnostic.reference_value,
        analytics_data_version=diagnostic.analytics_data_version,
        formula_version=diagnostic.formula_version,
        first_observed_at=first_observed_at,
        last_observed_at=last_observed_at,
        affected_from=affected_from,
        affected_to=affected_to,
        occurrence_count=len(items),
        representative_result_hash=representative.result.result_hash,
        result_hashes=tuple(sorted(item.result.result_hash for item in items)),
        rule_origins=origins,
        evidence=_merge_evidence(items),
        hypotheses=_merge_hypotheses(items),
        recommendations=_merge_recommendations(items),
        provenance=provenance,
    )


def _deduplicate(
    inputs: tuple[CorrelationInput, ...],
) -> tuple[DeduplicatedDiagnosticCandidate, ...]:
    grouped: dict[tuple[str, str, str, str, str], list[CorrelationInput]] = defaultdict(list)
    for item in inputs:
        grouped[_identity_key(item)].append(item)
    return tuple(
        _deduplicate_group(identity, tuple(values)) for identity, values in sorted(grouped.items())
    )


def _group_fingerprint(
    *,
    policy_code: str,
    policy_version: int,
    scope: EvaluationScope,
    domain: str,
    members: tuple[str, ...],
) -> str:
    return canonical_sha256(
        {
            "policy_code": policy_code,
            "policy_version": policy_version,
            "tenant_id": scope.tenant_id,
            "scope_type": scope.scope_type,
            "company_id": scope.company_id,
            "branch_id": scope.branch_id,
            "domain": domain,
            "member_fingerprints": list(members),
        }
    )


def _representative_diagnostic(
    items: tuple[DeduplicatedDiagnosticCandidate, ...],
) -> DeduplicatedDiagnosticCandidate:
    remaining = list(items)
    severity_rank = max(_SEVERITY_RANK[item.severity] for item in remaining)
    remaining = [item for item in remaining if _SEVERITY_RANK[item.severity] == severity_rank]
    priority = min(item.priority for item in remaining)
    remaining = [item for item in remaining if item.priority == priority]
    confidence = max(item.confidence_score for item in remaining)
    remaining = [item for item in remaining if item.confidence_score == confidence]
    latest_period = max(item.affected_to for item in remaining)
    remaining = [item for item in remaining if item.affected_to == latest_period]
    return min(
        remaining,
        key=lambda item: (
            item.diagnostic_code,
            str(item.rule_origins[0].rule_definition_id),
            item.representative_result_hash,
        ),
    )


def _build_cluster(
    items: tuple[DeduplicatedDiagnosticCandidate, ...],
    policy: CorrelationPolicyDefinition | None,
) -> DiagnosticClusterCandidate:
    if not items or len(items) > MAX_CLUSTER_MEMBERS:
        raise CorrelationValidationError("cluster member limit exceeded")
    scope = items[0].scope
    if any(_scope_key(item.scope) != _scope_key(scope) for item in items):
        raise CorrelationValidationError("cluster cannot cross authorized scopes")
    domains = {item.domain for item in items}
    if len(domains) != 1:
        raise CorrelationValidationError("cluster cannot mix diagnostic domains")
    representative = _representative_diagnostic(items)
    members = tuple(sorted(item.fingerprint for item in items))
    if policy is None:
        policy_code = _SINGLETON_POLICY_CODE
        policy_version = _SINGLETON_POLICY_VERSION
        policy_hash = _SINGLETON_POLICY_HASH
        reason = _SINGLETON_POLICY_REASON
    else:
        policy_code = policy.code
        policy_version = policy.version
        policy_hash = policy.policy_hash
        reason = policy.reason
    trace = CorrelationTraceEntry(
        policy_code=policy_code,
        policy_version=policy_version,
        policy_hash=policy_hash,
        reason=reason,
        member_fingerprints=members,
    )
    return DiagnosticClusterCandidate(
        cluster_fingerprint=_group_fingerprint(
            policy_code=policy_code,
            policy_version=policy_version,
            scope=scope,
            domain=representative.domain,
            members=members,
        ),
        policy_code=policy_code,
        policy_version=policy_version,
        policy_hash=policy_hash,
        domain=representative.domain,
        scope=scope,
        aggregate_severity=max(items, key=lambda item: _SEVERITY_RANK[item.severity]).severity,
        priority=min(item.priority for item in items),
        confidence_score=max(item.confidence_score for item in items),
        primary_diagnostic_fingerprint=representative.fingerprint,
        member_fingerprints=members,
        member_diagnostic_codes=tuple(sorted(item.diagnostic_code for item in items)),
        first_observed_at=min(item.first_observed_at for item in items),
        last_observed_at=max(item.last_observed_at for item in items),
        trace=(trace,),
    )


def _correlate_clusters(
    diagnostics: tuple[DeduplicatedDiagnosticCandidate, ...],
    policies: tuple[CorrelationPolicyDefinition, ...],
) -> tuple[DiagnosticClusterCandidate, ...]:
    by_code: dict[str, list[DeduplicatedDiagnosticCandidate]] = defaultdict(list)
    for diagnostic in diagnostics:
        by_code[diagnostic.diagnostic_code].append(diagnostic)
    consumed: set[tuple[str, str, str, str, str]] = set()
    clusters: list[DiagnosticClusterCandidate] = []
    for policy in policies:
        candidates = [
            item
            for code in policy.member_diagnostic_codes
            for item in by_code.get(code, ())
            if item.identity_key not in consumed
        ]
        partitions: dict[tuple[object, ...], list[DeduplicatedDiagnosticCandidate]] = defaultdict(
            list
        )
        for item in candidates:
            partitions[(*_scope_key(item.scope), item.affected_from, item.affected_to)].append(item)
        for _, partition in sorted(partitions.items(), key=lambda pair: pair[0]):
            distinct_codes = {item.diagnostic_code for item in partition}
            if len(distinct_codes) < 2:
                continue
            if len(partition) > MAX_CLUSTER_MEMBERS:
                raise CorrelationValidationError(f"policy {policy.code} exceeds group member limit")
            ordered = tuple(sorted(partition, key=lambda item: item.identity_key))
            clusters.append(_build_cluster(ordered, policy))
            consumed.update(item.identity_key for item in ordered)
    for diagnostic in diagnostics:
        if diagnostic.identity_key not in consumed:
            clusters.append(_build_cluster((diagnostic,), None))
    return tuple(sorted(clusters, key=lambda cluster: cluster.cluster_fingerprint))


def correlate_diagnostics(
    inputs: Iterable[CorrelationInput],
    *,
    policies: tuple[CorrelationPolicyDefinition, ...] = CORRELATION_POLICY_CATALOG,
) -> CorrelationBatchResult:
    """Validate, deduplicate and correlate a bounded batch without infrastructure access.

    Complexity is O(n log n + p log p): inputs are indexed by canonical identity and policies
    use diagnostic-code indexes. No unrestricted pairwise comparison is performed.
    """

    batch = tuple(islice(inputs, MAX_CORRELATION_INPUTS + 1))
    if len(batch) > MAX_CORRELATION_INPUTS:
        raise CorrelationValidationError("correlation batch input limit exceeded")
    ordered_policies = tuple(sorted(policies, key=lambda policy: policy.code))
    validate_correlation_policy_catalog(ordered_policies)
    accepted: list[CorrelationInput] = []
    counts = {"matched": 0, "not_matched": 0, "skipped": 0, "failed": 0}
    for item in batch:
        if not isinstance(item, CorrelationInput):
            raise CorrelationValidationError("all batch items must be CorrelationInput values")
        counts[item.result.state] += 1
        if _validate_result(item):
            accepted.append(item)
    diagnostics = _deduplicate(tuple(accepted))
    clusters = _correlate_clusters(diagnostics, ordered_policies)
    policy_catalog_hash = canonical_sha256([policy.as_dict() for policy in ordered_policies])
    metrics = CorrelationBatchMetrics(
        total_inputs=len(batch),
        matched_inputs=counts["matched"],
        not_matched_inputs=counts["not_matched"],
        skipped_inputs=counts["skipped"],
        failed_inputs=counts["failed"],
        accepted_occurrences=len(accepted),
        deduplicated_diagnostics=len(diagnostics),
        clusters=len(clusters),
    )
    provisional = CorrelationBatchResult(
        diagnostics=diagnostics,
        clusters=clusters,
        metrics=metrics,
        policy_catalog_hash=policy_catalog_hash,
    )
    return replace(
        provisional,
        batch_hash=canonical_sha256(provisional.as_dict(include_batch_hash=False)),
    )
