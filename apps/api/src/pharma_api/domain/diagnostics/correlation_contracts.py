"""Immutable contracts for deterministic diagnostic correlation and deduplication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pharma_api.domain.diagnostics.conditions import Severity
from pharma_api.domain.diagnostics.engine_contracts import (
    MAX_LOGIC_VERSION_LENGTH,
    MAX_METADATA_TEXT_LENGTH,
    MAX_RULE_ACTIONS,
    MAX_RULE_EVIDENCE,
    MAX_RULE_HYPOTHESES,
    MAX_STABLE_CODE_LENGTH,
    MAX_SUMMARY_LENGTH,
    MAX_TITLE_LENGTH,
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

CorrelationStatus = Literal["active"]
ScopeCompatibility = Literal["exact"]
TemporalCompatibility = Literal["same_affected_period"]
PrimarySelectionRule = Literal["severity_priority_confidence_recency_lexical"]
SeverityAggregationRule = Literal["maximum"]
PriorityAggregationRule = Literal["minimum"]

# A bounded batch supports all 120 governed rules across multiple authorized scopes while
# preventing unbounded memory use. Existing per-rule collection limits are reused below.
MAX_CORRELATION_INPUTS = 4_096
MAX_OCCURRENCES_PER_FINGERPRINT = 256
MAX_CORRELATION_POLICIES = 64
MAX_CLUSTER_MEMBERS = MAX_RULE_ACTIONS
MAX_CORRELATED_EVIDENCE = MAX_RULE_EVIDENCE
MAX_CORRELATED_HYPOTHESES = MAX_RULE_HYPOTHESES
MAX_CORRELATED_RECOMMENDATIONS = MAX_RULE_ACTIONS
CORRELATION_CONTRACT_VERSION = "b3a.1"
CORRELATION_ALGORITHM_VERSION = "b3a.1"


class CorrelationValidationError(ValueError):
    """Raised when correlation input or governed policy data is inconsistent."""


def _require_sha256(value: str, field: str) -> None:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise CorrelationValidationError(f"{field} must be a lowercase SHA-256 digest")


def _require_stable_code(value: str, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) > MAX_STABLE_CODE_LENGTH
        or STABLE_CODE_PATTERN.fullmatch(value) is None
    ):
        raise CorrelationValidationError(f"{field} must be a stable diagnostic code")


def _require_text(value: str, field: str, *, maximum: int = MAX_METADATA_TEXT_LENGTH) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CorrelationValidationError(f"{field} must be trimmed non-empty text")
    if len(value) > maximum:
        raise CorrelationValidationError(f"{field} exceeds {maximum} characters")


def _require_score(value: Decimal, field: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or not Decimal("0") <= value <= 1:
        raise CorrelationValidationError(f"{field} must be a finite Decimal between 0 and 1")


def _require_aware(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CorrelationValidationError(f"{field} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class CorrelationInput:
    """One explicit authorized scope paired with one deterministic evaluation result."""

    scope: EvaluationScope
    result: EvaluationResult

    def __post_init__(self) -> None:
        if not isinstance(self.scope, EvaluationScope):
            raise CorrelationValidationError("scope must be an EvaluationScope")
        if not isinstance(self.result, EvaluationResult):
            raise CorrelationValidationError("result must be an EvaluationResult")

    def as_dict(self) -> dict[str, object]:
        return {"scope": self.scope.as_dict(), "result": self.result.as_dict()}


@dataclass(frozen=True, slots=True)
class RuleOrigin:
    rule_definition_id: UUID
    rule_version_number: int

    def __post_init__(self) -> None:
        if not isinstance(self.rule_definition_id, UUID):
            raise CorrelationValidationError("rule_definition_id must be a UUID")
        if (
            isinstance(self.rule_version_number, bool)
            or not isinstance(self.rule_version_number, int)
            or self.rule_version_number < 1
        ):
            raise CorrelationValidationError("rule_version_number must be >= 1")

    def as_dict(self) -> dict[str, object]:
        return {
            "rule_definition_id": self.rule_definition_id,
            "rule_version_number": self.rule_version_number,
        }


@dataclass(frozen=True, slots=True)
class OccurrenceProvenance:
    result_hash: str
    rule_origin: RuleOrigin
    evaluated_at: datetime
    affected_from: datetime
    affected_to: datetime

    def __post_init__(self) -> None:
        _require_sha256(self.result_hash, "result_hash")
        _require_aware(self.evaluated_at, "evaluated_at")
        _require_aware(self.affected_from, "affected_from")
        _require_aware(self.affected_to, "affected_to")
        if self.affected_to < self.affected_from:
            raise CorrelationValidationError("occurrence affected period is inverted")

    def as_dict(self) -> dict[str, object]:
        return {
            "result_hash": self.result_hash,
            "rule_origin": self.rule_origin.as_dict(),
            "evaluated_at": self.evaluated_at,
            "affected_from": self.affected_from,
            "affected_to": self.affected_to,
        }


@dataclass(frozen=True, slots=True)
class CorrelatedHypothesis:
    """One stable hypothesis identity with complete immutable assessments preserved."""

    hypothesis_code: str
    logic_version: str
    assessments: tuple[HypothesisCandidate, ...]

    def __post_init__(self) -> None:
        _require_stable_code(self.hypothesis_code, "hypothesis_code")
        _require_text(
            self.logic_version,
            "logic_version",
            maximum=MAX_LOGIC_VERSION_LENGTH,
        )
        if not self.assessments:
            raise CorrelationValidationError("hypothesis assessments must not be empty")
        documents: list[str] = []
        for assessment in self.assessments:
            if not isinstance(assessment, HypothesisCandidate):
                raise CorrelationValidationError(
                    "hypothesis assessments must be HypothesisCandidate values"
                )
            if (
                assessment.hypothesis_code != self.hypothesis_code
                or assessment.logic_version != self.logic_version
            ):
                raise CorrelationValidationError(
                    "hypothesis assessment identity does not match its correlated identity"
                )
            documents.append(canonical_json(assessment.as_dict()))
        if tuple(sorted(set(documents))) != tuple(documents):
            raise CorrelationValidationError(
                "hypothesis assessments must be unique and canonically ordered"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "hypothesis_code": self.hypothesis_code,
            "logic_version": self.logic_version,
            "assessments": [item.as_dict() for item in self.assessments],
        }


@dataclass(frozen=True, slots=True)
class CorrelatedRecommendation:
    action_code: str
    action_version: int
    action_definition_hash: str
    title: str
    suggested_priority: int
    stable_orders: tuple[int, ...]
    rationales: tuple[str, ...]
    execution_mode: Literal["human_review_required"] = "human_review_required"
    requires_human_review: Literal[True] = True
    allows_automatic_financial_execution: Literal[False] = False

    def __post_init__(self) -> None:
        _require_stable_code(self.action_code, "action_code")
        _require_sha256(self.action_definition_hash, "action_definition_hash")
        _require_text(self.title, "recommendation title")
        if (
            isinstance(self.action_version, bool)
            or not isinstance(self.action_version, int)
            or self.action_version < 1
        ):
            raise CorrelationValidationError("action_version must be >= 1")
        if not 1 <= self.suggested_priority <= 4:
            raise CorrelationValidationError("suggested_priority must be between 1 and 4")
        if not self.rationales:
            raise CorrelationValidationError("recommendation rationales must not be empty")
        for rationale in self.rationales:
            _require_text(rationale, "recommendation rationale")
        if (
            self.execution_mode != "human_review_required"
            or self.requires_human_review is not True
            or self.allows_automatic_financial_execution is not False
        ):
            raise CorrelationValidationError("recommendation violates advisory-only guardrails")

    def as_dict(self) -> dict[str, object]:
        return {
            "action_code": self.action_code,
            "action_version": self.action_version,
            "action_definition_hash": self.action_definition_hash,
            "title": self.title,
            "suggested_priority": self.suggested_priority,
            "stable_orders": list(self.stable_orders),
            "rationales": list(self.rationales),
            "execution_mode": self.execution_mode,
            "requires_human_review": self.requires_human_review,
            "allows_automatic_financial_execution": self.allows_automatic_financial_execution,
        }


@dataclass(frozen=True, slots=True)
class DeduplicatedDiagnosticCandidate:
    scope: EvaluationScope
    fingerprint: str
    diagnostic_code: str
    domain: str
    title: str
    summary: str
    severity: Severity
    priority: int
    confidence_score: Decimal
    primary_kpi_code: str
    value_unit: str
    observed_value: Decimal | None
    reference_value: Decimal | None
    analytics_data_version: int
    formula_version: int
    first_observed_at: datetime
    last_observed_at: datetime
    affected_from: datetime
    affected_to: datetime
    occurrence_count: int
    representative_result_hash: str
    result_hashes: tuple[str, ...]
    rule_origins: tuple[RuleOrigin, ...]
    evidence: tuple[EvidenceCandidate, ...]
    hypotheses: tuple[CorrelatedHypothesis, ...]
    recommendations: tuple[CorrelatedRecommendation, ...]
    provenance: tuple[OccurrenceProvenance, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.fingerprint, "fingerprint")
        _require_sha256(self.representative_result_hash, "representative_result_hash")
        _require_stable_code(self.diagnostic_code, "diagnostic_code")
        _require_text(self.domain, "domain", maximum=32)
        _require_text(self.title, "title", maximum=MAX_TITLE_LENGTH)
        _require_text(self.summary, "summary", maximum=MAX_SUMMARY_LENGTH)
        _require_stable_code(self.primary_kpi_code, "primary_kpi_code")
        _require_text(self.value_unit, "value_unit", maximum=40)
        _require_aware(self.first_observed_at, "first_observed_at")
        _require_aware(self.last_observed_at, "last_observed_at")
        _require_aware(self.affected_from, "affected_from")
        _require_aware(self.affected_to, "affected_to")
        if self.last_observed_at < self.first_observed_at:
            raise CorrelationValidationError("diagnostic observation period is inverted")
        if self.affected_to < self.affected_from:
            raise CorrelationValidationError("diagnostic affected period is inverted")
        _require_score(self.confidence_score, "confidence_score")
        if not 1 <= self.priority <= 4:
            raise CorrelationValidationError("priority must be between 1 and 4")
        if self.occurrence_count < 1 or self.occurrence_count != len(self.provenance):
            raise CorrelationValidationError("occurrence_count must match provenance")
        if len(self.result_hashes) != self.occurrence_count:
            raise CorrelationValidationError("result_hashes must retain every occurrence")
        if len(self.evidence) > MAX_CORRELATED_EVIDENCE:
            raise CorrelationValidationError("correlated evidence limit exceeded")
        if len(self.hypotheses) > MAX_CORRELATED_HYPOTHESES:
            raise CorrelationValidationError("correlated hypothesis limit exceeded")
        if len(self.recommendations) > MAX_CORRELATED_RECOMMENDATIONS:
            raise CorrelationValidationError("correlated recommendation limit exceeded")

    @property
    def identity_key(self) -> tuple[str, str, str, str, str]:
        return (
            str(self.scope.tenant_id),
            self.scope.scope_type,
            "" if self.scope.company_id is None else str(self.scope.company_id),
            "" if self.scope.branch_id is None else str(self.scope.branch_id),
            self.fingerprint,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope.as_dict(),
            "fingerprint": self.fingerprint,
            "diagnostic_code": self.diagnostic_code,
            "domain": self.domain,
            "title": self.title,
            "summary": self.summary,
            "severity": self.severity,
            "priority": self.priority,
            "confidence_score": self.confidence_score,
            "primary_kpi_code": self.primary_kpi_code,
            "value_unit": self.value_unit,
            "observed_value": self.observed_value,
            "reference_value": self.reference_value,
            "analytics_data_version": self.analytics_data_version,
            "formula_version": self.formula_version,
            "first_observed_at": self.first_observed_at,
            "last_observed_at": self.last_observed_at,
            "affected_from": self.affected_from,
            "affected_to": self.affected_to,
            "occurrence_count": self.occurrence_count,
            "representative_result_hash": self.representative_result_hash,
            "result_hashes": list(self.result_hashes),
            "rule_origins": [item.as_dict() for item in self.rule_origins],
            "evidence": [item.as_dict() for item in self.evidence],
            "hypotheses": [item.as_dict() for item in self.hypotheses],
            "recommendations": [item.as_dict() for item in self.recommendations],
            "provenance": [item.as_dict() for item in self.provenance],
        }


@dataclass(frozen=True, slots=True)
class CorrelationPolicyDefinition:
    code: str
    version: int
    domains: tuple[str, ...]
    member_diagnostic_codes: tuple[str, ...]
    compatible_kpi_codes: tuple[str, ...]
    scope_compatibility: ScopeCompatibility
    temporal_compatibility: TemporalCompatibility
    reason: str
    primary_selection_rule: PrimarySelectionRule
    severity_aggregation_rule: SeverityAggregationRule
    priority_aggregation_rule: PriorityAggregationRule
    limitations: tuple[str, ...]
    status: CorrelationStatus = "active"

    def __post_init__(self) -> None:
        _require_stable_code(self.code, "policy code")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise CorrelationValidationError("policy version must be >= 1")
        if self.scope_compatibility != "exact":
            raise CorrelationValidationError("policy scope compatibility must be exact")
        if self.temporal_compatibility != "same_affected_period":
            raise CorrelationValidationError(
                "policy temporal compatibility must require the same affected period"
            )
        if self.primary_selection_rule != "severity_priority_confidence_recency_lexical":
            raise CorrelationValidationError("policy primary selection rule is unsupported")
        if self.severity_aggregation_rule != "maximum":
            raise CorrelationValidationError("policy severity aggregation rule is unsupported")
        if self.priority_aggregation_rule != "minimum":
            raise CorrelationValidationError("policy priority aggregation rule is unsupported")
        if self.status != "active":
            raise CorrelationValidationError("policy status must be active")
        if not 2 <= len(self.member_diagnostic_codes) <= MAX_CLUSTER_MEMBERS:
            raise CorrelationValidationError("policy must declare 2..MAX_CLUSTER_MEMBERS members")
        if tuple(sorted(set(self.member_diagnostic_codes))) != self.member_diagnostic_codes:
            raise CorrelationValidationError("policy members must be unique and lexically ordered")
        if tuple(sorted(set(self.compatible_kpi_codes))) != self.compatible_kpi_codes:
            raise CorrelationValidationError("policy KPIs must be unique and lexically ordered")
        if not self.domains or tuple(sorted(set(self.domains))) != self.domains:
            raise CorrelationValidationError("policy domains must be unique and lexically ordered")
        for member in self.member_diagnostic_codes:
            _require_stable_code(member, "policy member")
        for kpi in self.compatible_kpi_codes:
            _require_stable_code(kpi, "policy KPI")
        _require_text(self.reason, "policy reason")
        if not self.limitations:
            raise CorrelationValidationError("policy limitations must not be empty")
        for limitation in self.limitations:
            _require_text(limitation, "policy limitation")

    @property
    def policy_hash(self) -> str:
        return canonical_sha256(self.as_dict(include_policy_hash=False))

    def as_dict(self, *, include_policy_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "code": self.code,
            "version": self.version,
            "domains": list(self.domains),
            "member_diagnostic_codes": list(self.member_diagnostic_codes),
            "compatible_kpi_codes": list(self.compatible_kpi_codes),
            "scope_compatibility": self.scope_compatibility,
            "temporal_compatibility": self.temporal_compatibility,
            "reason": self.reason,
            "primary_selection_rule": self.primary_selection_rule,
            "severity_aggregation_rule": self.severity_aggregation_rule,
            "priority_aggregation_rule": self.priority_aggregation_rule,
            "limitations": list(self.limitations),
            "status": self.status,
        }
        if include_policy_hash:
            payload["policy_hash"] = self.policy_hash
        return payload


@dataclass(frozen=True, slots=True)
class CorrelationTraceEntry:
    policy_code: str
    policy_version: int
    policy_hash: str
    reason: str
    member_fingerprints: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_stable_code(self.policy_code, "trace policy code")
        if (
            isinstance(self.policy_version, bool)
            or not isinstance(self.policy_version, int)
            or self.policy_version < 1
        ):
            raise CorrelationValidationError("trace policy version must be >= 1")
        _require_sha256(self.policy_hash, "trace policy hash")
        _require_text(self.reason, "trace reason")

    def as_dict(self) -> dict[str, object]:
        return {
            "policy_code": self.policy_code,
            "policy_version": self.policy_version,
            "policy_hash": self.policy_hash,
            "reason": self.reason,
            "member_fingerprints": list(self.member_fingerprints),
        }


@dataclass(frozen=True, slots=True)
class DiagnosticClusterCandidate:
    cluster_fingerprint: str
    policy_code: str
    policy_version: int
    policy_hash: str
    domain: str
    scope: EvaluationScope
    aggregate_severity: Severity
    priority: int
    confidence_score: Decimal
    primary_diagnostic_fingerprint: str
    member_fingerprints: tuple[str, ...]
    member_diagnostic_codes: tuple[str, ...]
    first_observed_at: datetime
    last_observed_at: datetime
    trace: tuple[CorrelationTraceEntry, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.cluster_fingerprint, "cluster_fingerprint")
        _require_sha256(self.policy_hash, "policy_hash")
        _require_sha256(self.primary_diagnostic_fingerprint, "primary fingerprint")
        _require_stable_code(self.policy_code, "cluster policy code")
        _require_text(self.domain, "cluster domain", maximum=32)
        _require_aware(self.first_observed_at, "cluster first_observed_at")
        _require_aware(self.last_observed_at, "cluster last_observed_at")
        if self.last_observed_at < self.first_observed_at:
            raise CorrelationValidationError("cluster observation period is inverted")
        for diagnostic_code in self.member_diagnostic_codes:
            _require_stable_code(diagnostic_code, "cluster member diagnostic code")
        if not 1 <= len(self.member_fingerprints) <= MAX_CLUSTER_MEMBERS:
            raise CorrelationValidationError("cluster member limit exceeded")
        if tuple(sorted(set(self.member_fingerprints))) != self.member_fingerprints:
            raise CorrelationValidationError("cluster fingerprints must be unique and ordered")
        if self.primary_diagnostic_fingerprint not in self.member_fingerprints:
            raise CorrelationValidationError("primary diagnostic must be a cluster member")
        _require_score(self.confidence_score, "cluster confidence")
        if not 1 <= self.priority <= 4:
            raise CorrelationValidationError("cluster priority must be between 1 and 4")

    def as_dict(self) -> dict[str, object]:
        return {
            "cluster_fingerprint": self.cluster_fingerprint,
            "policy_code": self.policy_code,
            "policy_version": self.policy_version,
            "policy_hash": self.policy_hash,
            "domain": self.domain,
            "scope": self.scope.as_dict(),
            "aggregate_severity": self.aggregate_severity,
            "priority": self.priority,
            "confidence_score": self.confidence_score,
            "primary_diagnostic_fingerprint": self.primary_diagnostic_fingerprint,
            "member_fingerprints": list(self.member_fingerprints),
            "member_diagnostic_codes": list(self.member_diagnostic_codes),
            "first_observed_at": self.first_observed_at,
            "last_observed_at": self.last_observed_at,
            "trace": [item.as_dict() for item in self.trace],
        }


@dataclass(frozen=True, slots=True)
class CorrelationBatchMetrics:
    total_inputs: int
    matched_inputs: int
    not_matched_inputs: int
    skipped_inputs: int
    failed_inputs: int
    accepted_occurrences: int
    deduplicated_diagnostics: int
    clusters: int

    def __post_init__(self) -> None:
        values = (
            self.total_inputs,
            self.matched_inputs,
            self.not_matched_inputs,
            self.skipped_inputs,
            self.failed_inputs,
            self.accepted_occurrences,
            self.deduplicated_diagnostics,
            self.clusters,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values
        ):
            raise CorrelationValidationError("batch metrics must be non-negative integers")
        if (
            self.matched_inputs + self.not_matched_inputs + self.skipped_inputs + self.failed_inputs
            != self.total_inputs
        ):
            raise CorrelationValidationError("batch state metrics must sum to total_inputs")

    def as_dict(self) -> dict[str, object]:
        return {
            "total_inputs": self.total_inputs,
            "matched_inputs": self.matched_inputs,
            "not_matched_inputs": self.not_matched_inputs,
            "skipped_inputs": self.skipped_inputs,
            "failed_inputs": self.failed_inputs,
            "accepted_occurrences": self.accepted_occurrences,
            "deduplicated_diagnostics": self.deduplicated_diagnostics,
            "clusters": self.clusters,
        }


@dataclass(frozen=True, slots=True)
class CorrelationBatchResult:
    diagnostics: tuple[DeduplicatedDiagnosticCandidate, ...]
    clusters: tuple[DiagnosticClusterCandidate, ...]
    metrics: CorrelationBatchMetrics
    policy_catalog_hash: str
    algorithm_version: str = CORRELATION_ALGORITHM_VERSION
    batch_hash: str = ""

    def __post_init__(self) -> None:
        _require_sha256(self.policy_catalog_hash, "policy_catalog_hash")
        if self.batch_hash:
            _require_sha256(self.batch_hash, "batch_hash")

    def as_dict(self, *, include_batch_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "diagnostics": [item.as_dict() for item in self.diagnostics],
            "clusters": [item.as_dict() for item in self.clusters],
            "metrics": self.metrics.as_dict(),
            "policy_catalog_hash": self.policy_catalog_hash,
            "algorithm_version": self.algorithm_version,
        }
        if include_batch_hash:
            payload["batch_hash"] = self.batch_hash
        return payload

    def canonical_payload(self) -> str:
        return canonical_json(self.as_dict())


@dataclass(frozen=True, slots=True)
class CorrelationManifest:
    contract_version: str
    algorithm_version: str
    policy_count: int
    policy_catalog_hash: str
    limits: tuple[tuple[str, int], ...]

    @property
    def manifest_hash(self) -> str:
        return canonical_sha256(self.as_dict(include_manifest_hash=False))

    def as_dict(self, *, include_manifest_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "contract_version": self.contract_version,
            "algorithm_version": self.algorithm_version,
            "policy_count": self.policy_count,
            "policy_catalog_hash": self.policy_catalog_hash,
            "limits": [{"name": name, "value": value} for name, value in self.limits],
        }
        if include_manifest_hash:
            payload["manifest_hash"] = self.manifest_hash
        return payload


def recommendation_identity(
    item: ActionRecommendationCandidate,
) -> tuple[str, int, str]:
    """Return the governed immutable recommendation identity."""

    return item.action_code, item.action_version, item.action_definition_hash
