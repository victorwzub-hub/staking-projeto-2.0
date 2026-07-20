"""Pure deterministic evaluation core for governed diagnostic rules.

The module deliberately performs no I/O and imports no infrastructure.  A caller
supplies an immutable rule snapshot, an explicit evaluation timestamp and
already-resolved analytical observations.  The same semantic input therefore
produces the same outcome, trace, evidence, recommendations and hashes.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256
from typing import Literal, cast
from uuid import UUID

from pharma_api.domain.analytics.kpis import KPI_BY_CODE
from pharma_api.domain.diagnostics.actions import ACTION_BY_CODE, ActionDefinition
from pharma_api.domain.diagnostics.conditions import (
    MAX_PERIODS,
    MIN_PERIODS,
    AllOf,
    AnyOf,
    Between,
    ChangeOperand,
    Compare,
    Concentration,
    Condition,
    ConditionValidationError,
    DataAvailable,
    Fixed,
    Frequency,
    Kpi,
    KpiRef,
    MinQuality,
    MissingData,
    MovingAverage,
    Negate,
    Operand,
    Percentile,
    Persisted,
    RuleControls,
    Severity,
    Share,
    Trend,
    condition_kpi_dependencies,
    evaluate_predicate,
    parse_condition,
    parse_rule_controls,
    serialize_condition,
)

ScopeType = Literal["tenant", "company", "branch"]
RuleOwnershipType = Literal["system", "tenant"]
EvaluationState = Literal["matched", "not_matched", "skipped", "failed"]
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
EvidenceType = Literal[
    "kpi_value",
    "comparison",
    "trend",
    "threshold",
    "data_quality",
    "lineage",
]
EvidenceDirection = Literal[
    "above",
    "below",
    "equal",
    "increasing",
    "decreasing",
    "mixed",
    "not_applicable",
]
EvidenceSource = Literal[
    "analytics_kpi",
    "analytics_fact",
    "analytics_aggregate",
    "data_quality",
    "lineage",
]
EvidenceRelation = Literal["supports", "contradicts", "context"]
HypothesisStatus = Literal["supported", "contradicted", "inconclusive", "not_evaluated"]
TraceOutcome = Literal["true", "false", "indeterminate"]
ErrorCode = Literal[
    "missing_kpi",
    "unknown_kpi",
    "invalid_rule_snapshot",
    "unsupported_rule_version",
    "invalid_scope",
    "invalid_observation",
    "window_mismatch",
    "data_version_mismatch",
    "insufficient_data_quality",
    "condition_not_evaluable",
    "action_not_allowed",
    "internal_evaluation_error",
]

ENGINE_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
STABLE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MEASUREMENT_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]*$")

MIN_USABLE_DATA_QUALITY = Decimal("0.2500")
CONFIDENCE_QUANTUM = Decimal("0.0001")
VALUE_QUANTUM = Decimal("0.000001")

_SCOPE_TYPES = frozenset({"tenant", "company", "branch"})
_RULE_OWNERSHIP_TYPES = frozenset({"system", "tenant"})
_OBSERVATION_KINDS = frozenset(
    {
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
    }
)
_EVIDENCE_TYPES = frozenset(
    {"kpi_value", "comparison", "trend", "threshold", "data_quality", "lineage"}
)
_EVIDENCE_DIRECTIONS = frozenset(
    {"above", "below", "equal", "increasing", "decreasing", "mixed", "not_applicable"}
)
_EVIDENCE_SOURCES = frozenset(
    {"analytics_kpi", "analytics_fact", "analytics_aggregate", "data_quality", "lineage"}
)
_EVIDENCE_RELATIONS = frozenset({"supports", "contradicts", "context"})
_DIAGNOSTIC_DOMAINS = frozenset(
    {"inventory", "sales", "margin", "purchases", "suppliers", "operations"}
)

_SEVERITY_PRIORITY: Mapping[Severity, int] = {
    "info": 4,
    "low": 3,
    "medium": 2,
    "high": 1,
    "critical": 1,
}


class DiagnosticEngineValidationError(ValueError):
    """Raised for invalid immutable engine contracts before evaluation starts."""


class CanonicalizationError(ValueError):
    """Raised when a value cannot be represented by the canonical JSON contract."""


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise CanonicalizationError("non-finite Decimal values are forbidden")
    if value == 0:
        return "0"
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _datetime_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CanonicalizationError("naive datetimes are forbidden")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _normalize_canonical(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        raise CanonicalizationError("float values are forbidden; use Decimal")
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return _datetime_text(value)
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError("canonical mappings require string keys")
            normalized[key] = _normalize_canonical(item)
        return normalized
    if isinstance(value, (tuple, list)):
        return [_normalize_canonical(item) for item in value]
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        return _normalize_canonical(as_dict())
    raise CanonicalizationError(f"unsupported canonical value {type(value).__name__}")


def canonical_json(value: object) -> str:
    """Return stable UTF-8 JSON text for supported domain values."""

    return json.dumps(
        _normalize_canonical(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def canonical_sha256(value: object) -> str:
    """Return SHA-256 over the canonical UTF-8 JSON representation."""

    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DiagnosticEngineValidationError(f"{field} must be timezone-aware")


def _require_decimal_range(value: Decimal, field: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise DiagnosticEngineValidationError(f"{field} must be a finite Decimal")
    if not Decimal("0") <= value <= Decimal("1"):
        raise DiagnosticEngineValidationError(f"{field} must be between 0 and 1")


def _quantize_score(value: Decimal) -> Decimal:
    bounded = min(Decimal("1"), max(Decimal("0"), value))
    return bounded.quantize(CONFIDENCE_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class EvaluationScope:
    tenant_id: UUID
    scope_type: ScopeType
    company_id: UUID | None = None
    branch_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID):
            raise DiagnosticEngineValidationError("invalid_scope: tenant_id must be a UUID")
        if self.scope_type not in _SCOPE_TYPES:
            raise DiagnosticEngineValidationError("invalid_scope: unsupported scope_type")
        if self.company_id is not None and not isinstance(self.company_id, UUID):
            raise DiagnosticEngineValidationError("invalid_scope: company_id must be a UUID")
        if self.branch_id is not None and not isinstance(self.branch_id, UUID):
            raise DiagnosticEngineValidationError("invalid_scope: branch_id must be a UUID")
        valid = (
            (self.scope_type == "tenant" and self.company_id is None and self.branch_id is None)
            or (
                self.scope_type == "company"
                and self.company_id is not None
                and self.branch_id is None
            )
            or (
                self.scope_type == "branch"
                and self.company_id is not None
                and self.branch_id is not None
            )
        )
        if not valid:
            raise DiagnosticEngineValidationError("invalid_scope: incoherent company/branch scope")

    def as_dict(self) -> dict[str, object]:
        return {
            "tenant_id": str(self.tenant_id),
            "scope_type": self.scope_type,
            "company_id": None if self.company_id is None else str(self.company_id),
            "branch_id": None if self.branch_id is None else str(self.branch_id),
        }


@dataclass(frozen=True, slots=True)
class KPIObservation:
    kpi_code: str
    value: Decimal | None
    period_start: datetime
    period_end: datetime
    data_version: int
    source_type: EvidenceSource = "analytics_kpi"
    quality_score: Decimal = Decimal("1")
    coverage: Decimal = Decimal("1")
    lineage_ref: str | None = None
    formula_version: int = 1
    kind: ObservationKind = "current"
    parameter: int | Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kpi_code, str) or self.kpi_code not in KPI_BY_CODE:
            raise DiagnosticEngineValidationError(f"unknown KPI {self.kpi_code!r}")
        if self.kind not in _OBSERVATION_KINDS:
            raise DiagnosticEngineValidationError(f"unsupported observation kind {self.kind!r}")
        if self.source_type not in _EVIDENCE_SOURCES:
            raise DiagnosticEngineValidationError(
                f"unsupported evidence source {self.source_type!r}"
            )
        if self.value is not None and not isinstance(self.value, Decimal):
            raise DiagnosticEngineValidationError("observation value must be Decimal or None")
        if self.value is not None and not self.value.is_finite():
            raise DiagnosticEngineValidationError("observation value must be finite")
        _require_aware(self.period_start, "period_start")
        _require_aware(self.period_end, "period_end")
        if self.period_end < self.period_start:
            raise DiagnosticEngineValidationError("observation period_end precedes period_start")
        if (
            isinstance(self.data_version, bool)
            or not isinstance(self.data_version, int)
            or self.data_version < 0
        ):
            raise DiagnosticEngineValidationError("data_version must be a non-negative integer")
        if (
            isinstance(self.formula_version, bool)
            or not isinstance(self.formula_version, int)
            or self.formula_version < 1
        ):
            raise DiagnosticEngineValidationError("formula_version must be >= 1")
        _require_decimal_range(self.quality_score, "quality_score")
        _require_decimal_range(self.coverage, "coverage")
        if self.lineage_ref is not None and (
            not self.lineage_ref or self.lineage_ref != self.lineage_ref.strip()
        ):
            raise DiagnosticEngineValidationError("lineage_ref must be a trimmed non-empty string")
        parameterized = {"moving_average", "trend", "frequency", "concentration", "percentile"}
        if self.kind not in parameterized and self.parameter is not None:
            raise DiagnosticEngineValidationError(
                f"{self.kind} observations do not accept a parameter"
            )
        if self.kind in {"moving_average", "trend", "frequency"}:
            if (
                isinstance(self.parameter, bool)
                or not isinstance(self.parameter, int)
                or not MIN_PERIODS <= self.parameter <= MAX_PERIODS
            ):
                raise DiagnosticEngineValidationError(
                    f"{self.kind} parameter must be an integer between "
                    f"{MIN_PERIODS} and {MAX_PERIODS}"
                )
        elif self.kind == "concentration":
            if (
                isinstance(self.parameter, bool)
                or not isinstance(self.parameter, int)
                or not 1 <= self.parameter <= 50
            ):
                raise DiagnosticEngineValidationError(
                    "concentration parameter must be an integer between 1 and 50"
                )
        elif self.kind == "percentile":
            if not isinstance(self.parameter, Decimal) or not self.parameter.is_finite():
                raise DiagnosticEngineValidationError(
                    "percentile parameter must be a finite Decimal"
                )
            if not Decimal("0") <= self.parameter <= Decimal("100"):
                raise DiagnosticEngineValidationError(
                    "percentile parameter must be between 0 and 100"
                )

    @property
    def measurement_key(self) -> str:
        if self.kind == "current":
            return self.kpi_code
        if self.kind in {"moving_average", "trend", "frequency", "concentration"}:
            return f"{self.kind}:{self.kpi_code}:{self.parameter}"
        if self.kind == "percentile":
            assert isinstance(self.parameter, Decimal)
            return f"percentile:{self.kpi_code}:{_decimal_text(self.parameter)}"
        return f"{self.kind}:{self.kpi_code}"

    @property
    def unit(self) -> str:
        return KPI_BY_CODE[self.kpi_code].unit

    def as_dict(self) -> dict[str, object]:
        return {
            "measurement_key": self.measurement_key,
            "kpi_code": self.kpi_code,
            "kind": self.kind,
            "parameter": self.parameter,
            "value": self.value,
            "unit": self.unit,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "data_version": self.data_version,
            "source_type": self.source_type,
            "quality_score": self.quality_score,
            "coverage": self.coverage,
            "lineage_ref": self.lineage_ref,
            "formula_version": self.formula_version,
        }


@dataclass(frozen=True, slots=True)
class ObservationFrame:
    observations: tuple[KPIObservation, ...]

    def __post_init__(self) -> None:
        keys = [observation.measurement_key for observation in self.observations]
        if len(keys) != len(set(keys)):
            raise DiagnosticEngineValidationError(
                "history frame contains duplicate measurement keys"
            )

    def as_dict(self) -> dict[str, object]:
        return {"observations": [observation.as_dict() for observation in self.observations]}


@dataclass(frozen=True, slots=True)
class ActionReference:
    action_code: str
    action_version: int
    rationale: str
    suggested_priority: int | None = None

    def __post_init__(self) -> None:
        if STABLE_CODE_PATTERN.fullmatch(self.action_code) is None:
            raise DiagnosticEngineValidationError("invalid action code format")
        if (
            isinstance(self.action_version, bool)
            or not isinstance(self.action_version, int)
            or self.action_version < 1
        ):
            raise DiagnosticEngineValidationError("action_version must be >= 1")
        if not self.rationale or self.rationale != self.rationale.strip():
            raise DiagnosticEngineValidationError(
                "action rationale must be a trimmed non-empty string"
            )
        if self.suggested_priority is not None and self.suggested_priority not in {1, 2, 3, 4}:
            raise DiagnosticEngineValidationError("suggested_priority must be between 1 and 4")

    def as_dict(self) -> dict[str, object]:
        return {
            "action_code": self.action_code,
            "action_version": self.action_version,
            "rationale": self.rationale,
            "suggested_priority": self.suggested_priority,
        }


@dataclass(frozen=True, slots=True)
class EvidenceSpec:
    evidence_code: str
    evidence_type: EvidenceType
    kpi_code: str
    observation_key: str
    direction: EvidenceDirection
    relation: EvidenceRelation = "supports"
    reference_key: str | None = None
    weight: Decimal = Decimal("1")
    detail: str = "Observed analytical evidence."

    def __post_init__(self) -> None:
        if STABLE_CODE_PATTERN.fullmatch(self.evidence_code) is None:
            raise DiagnosticEngineValidationError("invalid evidence code format")
        if self.evidence_type not in _EVIDENCE_TYPES:
            raise DiagnosticEngineValidationError("unsupported evidence type")
        if self.direction not in _EVIDENCE_DIRECTIONS:
            raise DiagnosticEngineValidationError("unsupported evidence direction")
        if self.relation not in _EVIDENCE_RELATIONS:
            raise DiagnosticEngineValidationError("unsupported evidence relation")
        if self.kpi_code not in KPI_BY_CODE:
            raise DiagnosticEngineValidationError(f"unknown evidence KPI {self.kpi_code!r}")
        if MEASUREMENT_KEY_PATTERN.fullmatch(self.observation_key) is None:
            raise DiagnosticEngineValidationError("invalid observation_key")
        if (
            self.reference_key is not None
            and MEASUREMENT_KEY_PATTERN.fullmatch(self.reference_key) is None
        ):
            raise DiagnosticEngineValidationError("invalid reference_key")
        _require_decimal_range(self.weight, "evidence weight")
        if not self.detail or self.detail != self.detail.strip():
            raise DiagnosticEngineValidationError(
                "evidence detail must be a trimmed non-empty string"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "evidence_code": self.evidence_code,
            "evidence_type": self.evidence_type,
            "kpi_code": self.kpi_code,
            "observation_key": self.observation_key,
            "reference_key": self.reference_key,
            "direction": self.direction,
            "relation": self.relation,
            "weight": self.weight,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class HypothesisSpec:
    hypothesis_code: str
    explanation: str
    supporting_evidence_codes: tuple[str, ...] = ()
    contradicting_evidence_codes: tuple[str, ...] = ()
    logic_version: str = "1"
    minimum_support: Decimal = Decimal("0.5000")

    def __post_init__(self) -> None:
        if STABLE_CODE_PATTERN.fullmatch(self.hypothesis_code) is None:
            raise DiagnosticEngineValidationError("invalid hypothesis code format")
        if not self.explanation or self.explanation != self.explanation.strip():
            raise DiagnosticEngineValidationError("hypothesis explanation must be trimmed")
        if not self.logic_version or self.logic_version != self.logic_version.strip():
            raise DiagnosticEngineValidationError("logic_version must be trimmed")
        _require_decimal_range(self.minimum_support, "minimum_support")
        links = self.supporting_evidence_codes + self.contradicting_evidence_codes
        if len(links) != len(set(links)):
            raise DiagnosticEngineValidationError("hypothesis evidence links must be unique")
        if any(STABLE_CODE_PATTERN.fullmatch(code) is None for code in links):
            raise DiagnosticEngineValidationError("invalid hypothesis evidence code")

    def as_dict(self) -> dict[str, object]:
        return {
            "hypothesis_code": self.hypothesis_code,
            "explanation": self.explanation,
            "supporting_evidence_codes": list(self.supporting_evidence_codes),
            "contradicting_evidence_codes": list(self.contradicting_evidence_codes),
            "logic_version": self.logic_version,
            "minimum_support": self.minimum_support,
        }


def _definition_payload(
    *,
    rule_definition_id: UUID,
    version_number: int,
    ownership_type: RuleOwnershipType,
    rule_tenant_id: UUID | None,
    diagnostic_code: str,
    domain: str,
    title: str,
    summary: str,
    base_severity: Severity,
    primary_kpi_code: str,
    condition_document: object,
    condition_hash: str,
    declared_kpi_codes: tuple[str, ...],
    controls_document: object,
    actions: tuple[ActionReference, ...],
    evidence: tuple[EvidenceSpec, ...],
    hypotheses: tuple[HypothesisSpec, ...],
) -> dict[str, object]:
    return {
        "rule_definition_id": rule_definition_id,
        "version_number": version_number,
        "ownership_type": ownership_type,
        "rule_tenant_id": rule_tenant_id,
        "diagnostic_code": diagnostic_code,
        "domain": domain,
        "title": title,
        "summary": summary,
        "base_severity": base_severity,
        "primary_kpi_code": primary_kpi_code,
        "condition_document": condition_document,
        "condition_hash": condition_hash,
        "declared_kpi_codes": list(declared_kpi_codes),
        "controls_document": controls_document,
        "actions": [action.as_dict() for action in actions],
        "evidence": [item.as_dict() for item in evidence],
        "hypotheses": [item.as_dict() for item in hypotheses],
    }


@dataclass(frozen=True, slots=True)
class RuleSnapshot:
    rule_definition_id: UUID
    version_number: int
    ownership_type: RuleOwnershipType
    rule_tenant_id: UUID | None
    diagnostic_code: str
    domain: str
    title: str
    summary: str
    base_severity: Severity
    primary_kpi_code: str
    condition_json: str
    condition_hash: str
    definition_hash: str
    declared_kpi_codes: tuple[str, ...]
    controls_json: str
    actions: tuple[ActionReference, ...]
    evidence: tuple[EvidenceSpec, ...]
    hypotheses: tuple[HypothesisSpec, ...] = ()

    @classmethod
    def from_documents(
        cls,
        *,
        rule_definition_id: UUID,
        version_number: int,
        ownership_type: RuleOwnershipType,
        rule_tenant_id: UUID | None,
        diagnostic_code: str,
        domain: str,
        title: str,
        summary: str,
        base_severity: Severity,
        primary_kpi_code: str,
        condition_document: object,
        declared_kpi_codes: Sequence[str],
        controls_document: object | None = None,
        actions: Sequence[ActionReference] = (),
        evidence: Sequence[EvidenceSpec] = (),
        hypotheses: Sequence[HypothesisSpec] = (),
        condition_hash: str | None = None,
        definition_hash: str | None = None,
    ) -> RuleSnapshot:
        condition_json = canonical_json(condition_document)
        controls_json = canonical_json({} if controls_document is None else controls_document)
        actual_condition_hash = canonical_sha256(condition_document)
        raw_kpis = tuple(declared_kpi_codes)
        if len(raw_kpis) != len(set(raw_kpis)):
            raise DiagnosticEngineValidationError("declared KPI codes must be unique")
        kpis = tuple(sorted(raw_kpis))
        action_tuple = tuple(actions)
        evidence_tuple = tuple(evidence)
        hypothesis_tuple = tuple(hypotheses)
        payload = _definition_payload(
            rule_definition_id=rule_definition_id,
            version_number=version_number,
            ownership_type=ownership_type,
            rule_tenant_id=rule_tenant_id,
            diagnostic_code=diagnostic_code,
            domain=domain,
            title=title,
            summary=summary,
            base_severity=base_severity,
            primary_kpi_code=primary_kpi_code,
            condition_document=json.loads(condition_json),
            condition_hash=actual_condition_hash,
            declared_kpi_codes=kpis,
            controls_document=json.loads(controls_json),
            actions=action_tuple,
            evidence=evidence_tuple,
            hypotheses=hypothesis_tuple,
        )
        actual_definition_hash = canonical_sha256(payload)
        return cls(
            rule_definition_id=rule_definition_id,
            version_number=version_number,
            ownership_type=ownership_type,
            rule_tenant_id=rule_tenant_id,
            diagnostic_code=diagnostic_code,
            domain=domain,
            title=title,
            summary=summary,
            base_severity=base_severity,
            primary_kpi_code=primary_kpi_code,
            condition_json=condition_json,
            condition_hash=condition_hash or actual_condition_hash,
            definition_hash=definition_hash or actual_definition_hash,
            declared_kpi_codes=kpis,
            controls_json=controls_json,
            actions=action_tuple,
            evidence=evidence_tuple,
            hypotheses=hypothesis_tuple,
        )

    def __post_init__(self) -> None:
        if not isinstance(self.rule_definition_id, UUID):
            raise DiagnosticEngineValidationError("rule_definition_id must be a UUID")
        if (
            isinstance(self.version_number, bool)
            or not isinstance(self.version_number, int)
            or self.version_number < 1
        ):
            raise DiagnosticEngineValidationError("version_number must be >= 1")
        if self.ownership_type not in _RULE_OWNERSHIP_TYPES:
            raise DiagnosticEngineValidationError("unsupported rule ownership")
        if self.rule_tenant_id is not None and not isinstance(self.rule_tenant_id, UUID):
            raise DiagnosticEngineValidationError("rule_tenant_id must be a UUID")
        ownership_valid = (self.ownership_type == "system" and self.rule_tenant_id is None) or (
            self.ownership_type == "tenant" and self.rule_tenant_id is not None
        )
        if not ownership_valid:
            raise DiagnosticEngineValidationError("invalid rule ownership")
        if STABLE_CODE_PATTERN.fullmatch(self.diagnostic_code) is None:
            raise DiagnosticEngineValidationError("invalid diagnostic code format")
        if self.domain not in _DIAGNOSTIC_DOMAINS:
            raise DiagnosticEngineValidationError("unsupported diagnostic domain")
        if self.base_severity not in {"info", "low", "medium", "high", "critical"}:
            raise DiagnosticEngineValidationError("unsupported base severity")
        if self.primary_kpi_code not in KPI_BY_CODE:
            raise DiagnosticEngineValidationError("unknown primary KPI")
        if not self.title or self.title != self.title.strip():
            raise DiagnosticEngineValidationError("title must be a trimmed non-empty string")
        if not self.summary or self.summary != self.summary.strip():
            raise DiagnosticEngineValidationError("summary must be a trimmed non-empty string")
        if len(self.declared_kpi_codes) != len(set(self.declared_kpi_codes)):
            raise DiagnosticEngineValidationError("declared KPI codes must be unique")
        if self.declared_kpi_codes != tuple(sorted(self.declared_kpi_codes)):
            raise DiagnosticEngineValidationError("declared KPI codes must use lexical order")

    def condition_document(self) -> object:
        return json.loads(self.condition_json)

    def controls_document(self) -> object:
        return json.loads(self.controls_json)

    def computed_condition_hash(self) -> str:
        return canonical_sha256(self.condition_document())

    def computed_definition_hash(self) -> str:
        return canonical_sha256(
            _definition_payload(
                rule_definition_id=self.rule_definition_id,
                version_number=self.version_number,
                ownership_type=self.ownership_type,
                rule_tenant_id=self.rule_tenant_id,
                diagnostic_code=self.diagnostic_code,
                domain=self.domain,
                title=self.title,
                summary=self.summary,
                base_severity=self.base_severity,
                primary_kpi_code=self.primary_kpi_code,
                condition_document=self.condition_document(),
                condition_hash=self.computed_condition_hash(),
                declared_kpi_codes=self.declared_kpi_codes,
                controls_document=self.controls_document(),
                actions=self.actions,
                evidence=self.evidence,
                hypotheses=self.hypotheses,
            )
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **_definition_payload(
                rule_definition_id=self.rule_definition_id,
                version_number=self.version_number,
                ownership_type=self.ownership_type,
                rule_tenant_id=self.rule_tenant_id,
                diagnostic_code=self.diagnostic_code,
                domain=self.domain,
                title=self.title,
                summary=self.summary,
                base_severity=self.base_severity,
                primary_kpi_code=self.primary_kpi_code,
                condition_document=self.condition_document(),
                condition_hash=self.condition_hash,
                declared_kpi_codes=self.declared_kpi_codes,
                controls_document=self.controls_document(),
                actions=self.actions,
                evidence=self.evidence,
                hypotheses=self.hypotheses,
            ),
            "definition_hash": self.definition_hash,
        }


@dataclass(frozen=True, slots=True)
class RuleEvaluationInput:
    rule: RuleSnapshot
    scope: EvaluationScope
    window_start: datetime
    window_end: datetime
    analytics_data_version: int
    observations: tuple[KPIObservation, ...]
    evaluated_at: datetime
    engine_version: str
    history: tuple[ObservationFrame, ...] = ()

    def __post_init__(self) -> None:
        _require_aware(self.window_start, "window_start")
        _require_aware(self.window_end, "window_end")
        _require_aware(self.evaluated_at, "evaluated_at")
        if self.window_end < self.window_start:
            raise DiagnosticEngineValidationError(
                "window_mismatch: window_end precedes window_start"
            )
        if self.evaluated_at < self.window_end:
            raise DiagnosticEngineValidationError("evaluated_at cannot precede window_end")
        if (
            isinstance(self.analytics_data_version, bool)
            or not isinstance(self.analytics_data_version, int)
            or self.analytics_data_version < 0
        ):
            raise DiagnosticEngineValidationError("analytics_data_version must be non-negative")
        if ENGINE_VERSION_PATTERN.fullmatch(self.engine_version) is None:
            raise DiagnosticEngineValidationError("invalid engine_version")
        keys = [observation.measurement_key for observation in self.observations]
        if len(keys) != len(set(keys)):
            raise DiagnosticEngineValidationError("observations contain duplicate measurement keys")
        frame_ends: list[datetime] = []
        for frame in self.history:
            if not frame.observations:
                raise DiagnosticEngineValidationError("history frames must not be empty")
            frame_ends.append(max(item.period_end for item in frame.observations))
        if frame_ends != sorted(frame_ends):
            raise DiagnosticEngineValidationError("history frames must be chronological")


@dataclass(frozen=True, slots=True)
class EvaluationIssue:
    code: ErrorCode
    message: str

    def as_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class TraceEntry:
    path: str
    node_type: str
    outcome: TraceOutcome
    condition_json: str

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "node_type": self.node_type,
            "outcome": self.outcome,
            "condition": json.loads(self.condition_json),
        }


@dataclass(frozen=True, slots=True)
class EvidenceCandidate:
    evidence_code: str
    evidence_type: EvidenceType
    kpi_code: str
    observed_value: Decimal | None
    reference_value: Decimal | None
    unit: str
    period_start: datetime
    period_end: datetime
    direction: EvidenceDirection
    source_type: EvidenceSource
    analytics_data_version: int
    formula_version: int
    detail: str
    relation: EvidenceRelation
    weight: Decimal
    lineage_ref: str | None
    evidence_hash: str
    stable_order: int

    def as_dict(self) -> dict[str, object]:
        return {
            "evidence_code": self.evidence_code,
            "evidence_type": self.evidence_type,
            "kpi_code": self.kpi_code,
            "observed_value": self.observed_value,
            "reference_value": self.reference_value,
            "unit": self.unit,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "direction": self.direction,
            "source_type": self.source_type,
            "analytics_data_version": self.analytics_data_version,
            "formula_version": self.formula_version,
            "detail": self.detail,
            "relation": self.relation,
            "weight": self.weight,
            "lineage_ref": self.lineage_ref,
            "evidence_hash": self.evidence_hash,
            "stable_order": self.stable_order,
        }


@dataclass(frozen=True, slots=True)
class HypothesisCandidate:
    hypothesis_code: str
    evaluation_status: HypothesisStatus
    confidence_score: Decimal | None
    rank: int
    supporting_evidence_codes: tuple[str, ...]
    contradicting_evidence_codes: tuple[str, ...]
    explanation: str
    logic_version: str
    evaluated_at: datetime | None

    def as_dict(self) -> dict[str, object]:
        return {
            "hypothesis_code": self.hypothesis_code,
            "evaluation_status": self.evaluation_status,
            "confidence_score": self.confidence_score,
            "rank": self.rank,
            "supporting_evidence_codes": list(self.supporting_evidence_codes),
            "contradicting_evidence_codes": list(self.contradicting_evidence_codes),
            "explanation": self.explanation,
            "logic_version": self.logic_version,
            "evaluated_at": self.evaluated_at,
        }


@dataclass(frozen=True, slots=True)
class ActionRecommendationCandidate:
    action_code: str
    action_version: int
    title: str
    suggested_priority: int
    stable_order: int
    rationale: str
    execution_mode: Literal["human_review_required"] = "human_review_required"
    requires_human_review: Literal[True] = True
    allows_automatic_financial_execution: Literal[False] = False
    action_definition_hash: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "action_code": self.action_code,
            "action_version": self.action_version,
            "title": self.title,
            "suggested_priority": self.suggested_priority,
            "stable_order": self.stable_order,
            "rationale": self.rationale,
            "execution_mode": self.execution_mode,
            "requires_human_review": self.requires_human_review,
            "allows_automatic_financial_execution": self.allows_automatic_financial_execution,
            "action_definition_hash": self.action_definition_hash,
        }


@dataclass(frozen=True, slots=True)
class DiagnosticCandidate:
    diagnostic_code: str
    fingerprint: str
    domain: str
    title: str
    summary: str
    severity: Severity
    confidence_score: Decimal
    priority: int
    detected_at: datetime
    affected_from: datetime
    affected_to: datetime
    primary_kpi_code: str
    observed_value: Decimal | None
    reference_value: Decimal | None
    value_unit: str
    analytics_data_version: int
    formula_version: int

    def as_dict(self) -> dict[str, object]:
        return {
            "diagnostic_code": self.diagnostic_code,
            "fingerprint": self.fingerprint,
            "domain": self.domain,
            "title": self.title,
            "summary": self.summary,
            "severity": self.severity,
            "confidence_score": self.confidence_score,
            "priority": self.priority,
            "detected_at": self.detected_at,
            "affected_from": self.affected_from,
            "affected_to": self.affected_to,
            "primary_kpi_code": self.primary_kpi_code,
            "observed_value": self.observed_value,
            "reference_value": self.reference_value,
            "value_unit": self.value_unit,
            "analytics_data_version": self.analytics_data_version,
            "formula_version": self.formula_version,
        }


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    state: EvaluationState
    rule_definition_id: UUID
    rule_version_number: int
    engine_version: str
    evaluated_at: datetime
    dependencies: tuple[str, ...]
    observations: tuple[KPIObservation, ...]
    trace: tuple[TraceEntry, ...]
    diagnostic: DiagnosticCandidate | None = None
    evidence: tuple[EvidenceCandidate, ...] = ()
    hypotheses: tuple[HypothesisCandidate, ...] = ()
    recommendations: tuple[ActionRecommendationCandidate, ...] = ()
    issue: EvaluationIssue | None = None
    result_hash: str = ""

    @property
    def fingerprint(self) -> str | None:
        return None if self.diagnostic is None else self.diagnostic.fingerprint

    def as_dict(self, *, include_result_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "state": self.state,
            "rule_definition_id": self.rule_definition_id,
            "rule_version_number": self.rule_version_number,
            "engine_version": self.engine_version,
            "evaluated_at": self.evaluated_at,
            "dependencies": list(self.dependencies),
            "observations": [observation.as_dict() for observation in self.observations],
            "trace": [entry.as_dict() for entry in self.trace],
            "diagnostic": None if self.diagnostic is None else self.diagnostic.as_dict(),
            "evidence": [item.as_dict() for item in self.evidence],
            "hypotheses": [item.as_dict() for item in self.hypotheses],
            "recommendations": [item.as_dict() for item in self.recommendations],
            "issue": None if self.issue is None else self.issue.as_dict(),
        }
        if include_result_hash:
            payload["result_hash"] = self.result_hash
        return payload

    def canonical_payload(self) -> str:
        return canonical_json(self.as_dict())


def _finalize_result(result: EvaluationResult) -> EvaluationResult:
    digest = canonical_sha256(result.as_dict(include_result_hash=False))
    return replace(result, result_hash=digest)


def _result(
    evaluation: RuleEvaluationInput,
    *,
    state: EvaluationState,
    dependencies: tuple[str, ...] = (),
    observations: tuple[KPIObservation, ...] = (),
    trace: tuple[TraceEntry, ...] = (),
    diagnostic: DiagnosticCandidate | None = None,
    evidence: tuple[EvidenceCandidate, ...] = (),
    hypotheses: tuple[HypothesisCandidate, ...] = (),
    recommendations: tuple[ActionRecommendationCandidate, ...] = (),
    issue: EvaluationIssue | None = None,
) -> EvaluationResult:
    return _finalize_result(
        EvaluationResult(
            state=state,
            rule_definition_id=evaluation.rule.rule_definition_id,
            rule_version_number=evaluation.rule.version_number,
            engine_version=evaluation.engine_version,
            evaluated_at=evaluation.evaluated_at,
            dependencies=dependencies,
            observations=observations,
            trace=trace,
            diagnostic=diagnostic,
            evidence=evidence,
            hypotheses=hypotheses,
            recommendations=recommendations,
            issue=issue,
        )
    )


def _issue(code: ErrorCode, message: str) -> EvaluationIssue:
    return EvaluationIssue(code=code, message=message)


def _operand_key(operand: Operand) -> str | None:
    if isinstance(operand, Fixed):
        return None
    if isinstance(operand, Kpi):
        return operand.kpi_code
    if isinstance(operand, (MovingAverage, Trend, Frequency)):
        return f"{operand.node_type}:{operand.kpi_code}:{operand.periods}"
    if isinstance(operand, Concentration):
        return f"concentration:{operand.kpi_code}:{operand.top_n}"
    if isinstance(operand, Percentile):
        return f"percentile:{operand.kpi_code}:{_decimal_text(operand.p)}"
    if isinstance(operand, Share):
        return None
    if isinstance(operand, ChangeOperand):
        return operand.kpi_code
    if isinstance(operand, KpiRef):
        return f"{operand.node_type}:{operand.kpi_code}"
    return None


@dataclass(frozen=True, slots=True)
class _MeasurementPlan:
    required_current: tuple[str, ...]
    semantic_current: tuple[str, ...]
    semantic_history: tuple[str, ...]
    current_quality: bool
    history_quality: bool
    quality_aware: bool


def _measurement_plan(condition: Condition, rule: RuleSnapshot) -> _MeasurementPlan:
    required_current: set[str] = set()
    semantic_current: set[str] = set()
    semantic_history: set[str] = set()
    current_quality = False
    history_quality = False
    quality_aware = False

    def add_operand(operand_node: Operand, *, history: bool, required: bool) -> None:
        semantic = semantic_history if history else semantic_current
        keys: tuple[str, ...]
        if isinstance(operand_node, Share):
            keys = (operand_node.numerator_kpi, operand_node.denominator_kpi)
        elif isinstance(operand_node, ChangeOperand):
            keys = (
                operand_node.kpi_code,
                f"{operand_node.baseline}:{operand_node.kpi_code}",
            )
        else:
            key = _operand_key(operand_node)
            keys = () if key is None else (key,)
        semantic.update(keys)
        if required and not history:
            required_current.update(keys)

    def visit(node: Condition, *, history: bool = False) -> None:
        nonlocal current_quality, history_quality, quality_aware
        if isinstance(node, Compare):
            add_operand(node.left, history=history, required=True)
            add_operand(node.right, history=history, required=True)
        elif isinstance(node, Between):
            add_operand(node.value, history=history, required=True)
            add_operand(node.minimum, history=history, required=True)
            add_operand(node.maximum, history=history, required=True)
        elif isinstance(node, Persisted):
            visit(node.predicate, history=True)
        elif isinstance(node, DataAvailable):
            target = semantic_history if history else semantic_current
            target.add(node.kpi_code)
            if not history:
                required_current.add(node.kpi_code)
        elif isinstance(node, MinQuality):
            if history:
                history_quality = True
            else:
                current_quality = True
            quality_aware = True
        elif isinstance(node, MissingData):
            target = semantic_history if history else semantic_current
            target.add(node.kpi_code)
            quality_aware = True
        elif isinstance(node, (AllOf, AnyOf)):
            for child in node.nodes:
                visit(child, history=history)
        elif isinstance(node, Negate):
            visit(node.node, history=history)

    visit(condition)
    semantic_current.add(rule.primary_kpi_code)
    for spec in rule.evidence:
        semantic_current.add(spec.observation_key)
        if spec.reference_key is not None:
            semantic_current.add(spec.reference_key)
    return _MeasurementPlan(
        required_current=tuple(sorted(required_current)),
        semantic_current=tuple(sorted(semantic_current)),
        semantic_history=tuple(sorted(semantic_history)),
        current_quality=current_quality,
        history_quality=history_quality,
        quality_aware=quality_aware,
    )


def _selected_observations(
    observations: Sequence[KPIObservation],
    *,
    keys: tuple[str, ...],
    include_declared_quality: bool,
    declared_kpis: tuple[str, ...],
) -> tuple[KPIObservation, ...]:
    key_set = set(keys)
    declared_set = set(declared_kpis)
    return tuple(
        observation
        for observation in sorted(observations, key=lambda item: item.measurement_key)
        if observation.measurement_key in key_set
        or (include_declared_quality and observation.kpi_code in declared_set)
    )


def _build_frame_measurements(
    frame: ObservationFrame,
    *,
    plan: _MeasurementPlan,
    declared_kpis: tuple[str, ...],
) -> dict[str, object]:
    selected = _selected_observations(
        frame.observations,
        keys=plan.semantic_history,
        include_declared_quality=plan.history_quality,
        declared_kpis=declared_kpis,
    )
    measurements: dict[str, object] = {}
    qualities: list[Decimal] = []
    for observation in selected:
        measurements[observation.measurement_key] = observation.value
        if observation.kind == "current":
            measurements[f"coverage:{observation.kpi_code}"] = observation.coverage
        qualities.append(observation.quality_score)
    if qualities:
        measurements["quality_score"] = sum(qualities, Decimal("0")) / len(qualities)
    return measurements


def _build_measurements(
    evaluation: RuleEvaluationInput,
    plan: _MeasurementPlan,
) -> tuple[dict[str, object], dict[str, KPIObservation], Decimal, Decimal, Decimal]:
    ordered = tuple(sorted(evaluation.observations, key=lambda item: item.measurement_key))
    by_key = {observation.measurement_key: observation for observation in ordered}
    measurements: dict[str, object] = {}
    for observation in ordered:
        measurements[observation.measurement_key] = observation.value
        if observation.kind == "current":
            measurements[f"coverage:{observation.kpi_code}"] = observation.coverage
    relevant = _selected_observations(
        ordered,
        keys=plan.semantic_current,
        include_declared_quality=plan.current_quality,
        declared_kpis=evaluation.rule.declared_kpi_codes,
    )
    if relevant:
        quality = sum((item.quality_score for item in relevant), Decimal("0")) / len(relevant)
        coverage = sum((item.coverage for item in relevant), Decimal("0")) / len(relevant)
        lineage = Decimal(sum(item.lineage_ref is not None for item in relevant)) / Decimal(
            len(relevant)
        )
    else:
        quality = Decimal("0")
        coverage = Decimal("0")
        lineage = Decimal("0")
    measurements["quality_score"] = quality
    if evaluation.history:
        measurements["history"] = [
            _build_frame_measurements(
                frame,
                plan=plan,
                declared_kpis=evaluation.rule.declared_kpi_codes,
            )
            for frame in evaluation.history
        ]
    return measurements, by_key, quality, coverage, lineage


def _trace_outcome(value: bool | None) -> TraceOutcome:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "indeterminate"


def _trace_condition(
    condition: Condition, measurements: Mapping[str, object], path: str = "$"
) -> tuple[bool | None, tuple[TraceEntry, ...]]:
    value = evaluate_predicate(condition, measurements)
    entries: list[TraceEntry] = [
        TraceEntry(
            path=path,
            node_type=condition.node_type,
            outcome=_trace_outcome(value),
            condition_json=canonical_json(serialize_condition(condition)),
        )
    ]
    if isinstance(condition, (AllOf, AnyOf)):
        for index, child in enumerate(condition.nodes):
            _, child_entries = _trace_condition(child, measurements, f"{path}.nodes[{index}]")
            entries.extend(child_entries)
    elif isinstance(condition, Negate):
        _, child_entries = _trace_condition(condition.node, measurements, f"{path}.node")
        entries.extend(child_entries)
    return value, tuple(entries)


def _validate_snapshot(
    evaluation: RuleEvaluationInput,
) -> tuple[Condition, RuleControls, tuple[str, ...], _MeasurementPlan] | EvaluationIssue:
    rule = evaluation.rule
    if not SHA256_PATTERN.fullmatch(rule.condition_hash):
        return _issue("invalid_rule_snapshot", "condition_hash is not a lowercase SHA-256")
    if not SHA256_PATTERN.fullmatch(rule.definition_hash):
        return _issue("invalid_rule_snapshot", "definition_hash is not a lowercase SHA-256")
    try:
        condition_document = rule.condition_document()
        controls_document = rule.controls_document()
        computed_condition_hash = rule.computed_condition_hash()
        computed_definition_hash = rule.computed_definition_hash()
        condition = parse_condition(condition_document)
        controls = parse_rule_controls(controls_document)
    except (ConditionValidationError, CanonicalizationError, TypeError, ValueError) as exc:
        return _issue("invalid_rule_snapshot", str(exc))
    if computed_condition_hash != rule.condition_hash:
        return _issue(
            "invalid_rule_snapshot", "condition hash does not match the canonical document"
        )
    if computed_definition_hash != rule.definition_hash:
        return _issue(
            "invalid_rule_snapshot", "definition hash does not match the canonical snapshot"
        )
    if rule.version_number < 1:
        return _issue("unsupported_rule_version", "rule version must be >= 1")
    if rule.ownership_type == "tenant" and rule.rule_tenant_id != evaluation.scope.tenant_id:
        return _issue("invalid_scope", "tenant-owned rule belongs to another tenant")
    dependencies = condition_kpi_dependencies(condition)
    unknown = sorted(code for code in rule.declared_kpi_codes if code not in KPI_BY_CODE)
    if unknown:
        return _issue("unknown_kpi", f"unknown declared KPI codes: {unknown}")
    if not set(dependencies).issubset(rule.declared_kpi_codes):
        missing = sorted(set(dependencies) - set(rule.declared_kpi_codes))
        return _issue("invalid_rule_snapshot", f"condition dependencies not declared: {missing}")
    if rule.primary_kpi_code not in rule.declared_kpi_codes:
        return _issue("invalid_rule_snapshot", "primary KPI must be declared by the rule")
    evidence_codes = {item.evidence_code for item in rule.evidence}
    if len(evidence_codes) != len(rule.evidence):
        return _issue("invalid_rule_snapshot", "evidence codes must be unique")
    undeclared_evidence = sorted(
        {item.kpi_code for item in rule.evidence} - set(rule.declared_kpi_codes)
    )
    if undeclared_evidence:
        return _issue(
            "invalid_rule_snapshot",
            f"evidence KPI codes are not declared: {undeclared_evidence}",
        )
    action_codes = [item.action_code for item in rule.actions]
    if len(action_codes) != len(set(action_codes)):
        return _issue("invalid_rule_snapshot", "action codes must be unique")
    for reference in rule.actions:
        action = _action_definition(reference)
        if isinstance(action, EvaluationIssue):
            return action
    hypothesis_codes = [item.hypothesis_code for item in rule.hypotheses]
    if len(hypothesis_codes) != len(set(hypothesis_codes)):
        return _issue("invalid_rule_snapshot", "hypothesis codes must be unique")
    for hypothesis in rule.hypotheses:
        linked = set(hypothesis.supporting_evidence_codes + hypothesis.contradicting_evidence_codes)
        if not linked.issubset(evidence_codes):
            return _issue("invalid_rule_snapshot", "hypothesis references unknown evidence")
    plan = _measurement_plan(condition, rule)
    return condition, controls, dependencies, plan


def _validate_observations(
    evaluation: RuleEvaluationInput,
) -> EvaluationIssue | None:
    for observation in evaluation.observations:
        if observation.data_version != evaluation.analytics_data_version:
            return _issue(
                "data_version_mismatch",
                f"{observation.measurement_key} uses data version {observation.data_version}",
            )
        if observation.kind == "current" and (
            observation.period_start < evaluation.window_start
            or observation.period_end > evaluation.window_end
        ):
            return _issue(
                "window_mismatch",
                f"{observation.measurement_key} is outside the evaluation window",
            )
        if observation.period_end > evaluation.window_end:
            return _issue(
                "window_mismatch",
                f"{observation.measurement_key} ends after the evaluation window",
            )
    for frame in evaluation.history:
        for observation in frame.observations:
            if observation.data_version != evaluation.analytics_data_version:
                return _issue("data_version_mismatch", "history observation data version differs")
            if observation.period_end > evaluation.window_end:
                return _issue("window_mismatch", "history observation ends after the window")
    return None


def _action_definition(reference: ActionReference) -> ActionDefinition | EvaluationIssue:
    action = ACTION_BY_CODE.get(reference.action_code)
    if action is None:
        return _issue("action_not_allowed", f"unknown action {reference.action_code!r}")
    if action.version != reference.action_version:
        return _issue(
            "action_not_allowed",
            f"action {reference.action_code!r} version {reference.action_version} is not governed",
        )
    if (
        action.execution_mode != "human_review_required"
        or action.allows_automatic_financial_execution
        or action.status != "active"
    ):
        return _issue(
            "action_not_allowed", f"action {reference.action_code!r} is not safely usable"
        )
    return action


def _build_evidence(
    rule: RuleSnapshot,
    by_key: Mapping[str, KPIObservation],
) -> tuple[tuple[EvidenceCandidate, ...], EvaluationIssue | None]:
    candidates: list[EvidenceCandidate] = []
    for index, spec in enumerate(rule.evidence):
        observation = by_key.get(spec.observation_key)
        if observation is None:
            return (), _issue(
                "missing_kpi", f"missing evidence observation {spec.observation_key!r}"
            )
        if observation.kpi_code != spec.kpi_code:
            return (), _issue(
                "invalid_rule_snapshot",
                f"evidence {spec.evidence_code!r} uses an observation from another KPI",
            )
        reference = None if spec.reference_key is None else by_key.get(spec.reference_key)
        if spec.reference_key is not None and reference is None:
            return (), _issue("missing_kpi", f"missing evidence reference {spec.reference_key!r}")
        reference_value = None if reference is None else reference.value
        payload = {
            "evidence_code": spec.evidence_code,
            "evidence_type": spec.evidence_type,
            "kpi_code": spec.kpi_code,
            "observed_value": observation.value,
            "reference_value": reference_value,
            "unit": observation.unit,
            "period_start": observation.period_start,
            "period_end": observation.period_end,
            "direction": spec.direction,
            "source_type": observation.source_type,
            "analytics_data_version": observation.data_version,
            "formula_version": observation.formula_version,
            "detail": spec.detail,
            "relation": spec.relation,
            "weight": spec.weight,
            "lineage_ref": observation.lineage_ref,
            "stable_order": index,
        }
        candidates.append(
            EvidenceCandidate(
                evidence_code=spec.evidence_code,
                evidence_type=spec.evidence_type,
                kpi_code=spec.kpi_code,
                observed_value=observation.value,
                reference_value=reference_value,
                unit=observation.unit,
                period_start=observation.period_start,
                period_end=observation.period_end,
                direction=spec.direction,
                source_type=observation.source_type,
                analytics_data_version=observation.data_version,
                formula_version=observation.formula_version,
                detail=spec.detail,
                relation=spec.relation,
                weight=spec.weight,
                lineage_ref=observation.lineage_ref,
                evidence_hash=canonical_sha256(payload),
                stable_order=index,
            )
        )
    return tuple(candidates), None


def _confidence(
    *,
    quality: Decimal,
    coverage: Decimal,
    lineage: Decimal,
    evidence: tuple[EvidenceCandidate, ...],
) -> Decimal:
    """Calculate an explicit bounded score using only governed deterministic weights.

    Quality contributes 55%, coverage 20%, lineage availability 15%, and the
    factual support ratio 10%.  Contradicting evidence then subtracts up to 25%.
    Consequently missing or poor data can never increase confidence.
    """

    support = sum((item.weight for item in evidence if item.relation == "supports"), Decimal("0"))
    contradiction = sum(
        (item.weight for item in evidence if item.relation == "contradicts"), Decimal("0")
    )
    total = support + contradiction
    support_ratio = Decimal("0") if total == 0 else support / total
    contradiction_penalty = min(Decimal("0.25"), contradiction * Decimal("0.10"))
    raw = (
        quality * Decimal("0.55")
        + coverage * Decimal("0.20")
        + lineage * Decimal("0.15")
        + support_ratio * Decimal("0.10")
        - contradiction_penalty
    )
    return _quantize_score(raw)


def _severity(
    rule: RuleSnapshot,
    controls: RuleControls,
    by_key: Mapping[str, KPIObservation],
) -> Severity:
    if not controls.severity_ladder:
        return rule.base_severity
    reference_spec = next((item for item in rule.evidence if item.reference_key is not None), None)
    if reference_spec is None:
        return rule.base_severity
    observed = by_key.get(reference_spec.observation_key)
    reference = by_key.get(cast(str, reference_spec.reference_key))
    if (
        observed is None
        or reference is None
        or observed.value is None
        or reference.value in {None, Decimal("0")}
    ):
        return rule.base_severity
    assert reference.value is not None
    deviation = abs((observed.value - reference.value) / reference.value * Decimal("100"))
    selected = rule.base_severity
    for step in controls.severity_ladder:
        if deviation >= step.threshold_pct:
            selected = step.severity
    return selected


def _priority(
    severity: Severity,
    confidence: Decimal,
    actions: tuple[ActionRecommendationCandidate, ...],
) -> int:
    """Combine severity, governed action impact and confidence into priority 1..4."""

    impact_priority = min((item.suggested_priority for item in actions), default=4)
    base = min(_SEVERITY_PRIORITY[severity], impact_priority)
    if confidence < Decimal("0.5000"):
        base += 1
    elif confidence >= Decimal("0.8500"):
        base -= 1
    return max(1, min(4, base))


def _build_recommendations(
    rule: RuleSnapshot,
) -> tuple[tuple[ActionRecommendationCandidate, ...], EvaluationIssue | None]:
    candidates: list[ActionRecommendationCandidate] = []
    for index, reference in enumerate(rule.actions):
        definition = _action_definition(reference)
        if isinstance(definition, EvaluationIssue):
            return (), definition
        priority = reference.suggested_priority or definition.default_priority
        candidates.append(
            ActionRecommendationCandidate(
                action_code=definition.code,
                action_version=definition.version,
                title=definition.title,
                suggested_priority=priority,
                stable_order=index,
                rationale=reference.rationale,
                action_definition_hash=canonical_sha256(definition.as_dict()),
            )
        )
    return tuple(candidates), None


def _build_hypotheses(
    rule: RuleSnapshot,
    evidence: tuple[EvidenceCandidate, ...],
    overall_confidence: Decimal,
    evaluated_at: datetime,
) -> tuple[HypothesisCandidate, ...]:
    evidence_by_code = {item.evidence_code: item for item in evidence}
    candidates: list[HypothesisCandidate] = []
    for rank, spec in enumerate(rule.hypotheses, start=1):
        support_codes = tuple(
            code for code in spec.supporting_evidence_codes if code in evidence_by_code
        )
        contradict_codes = tuple(
            code for code in spec.contradicting_evidence_codes if code in evidence_by_code
        )
        support = sum((evidence_by_code[code].weight for code in support_codes), Decimal("0"))
        contradiction = sum(
            (evidence_by_code[code].weight for code in contradict_codes), Decimal("0")
        )
        total = support + contradiction
        if total == 0:
            status: HypothesisStatus = "not_evaluated"
            score = None
            timestamp = None
        else:
            support_ratio = support / total
            score = _quantize_score(overall_confidence * support_ratio)
            timestamp = evaluated_at
            if contradiction > support:
                status = "contradicted"
            elif support_ratio >= spec.minimum_support and support > contradiction:
                status = "supported"
            else:
                status = "inconclusive"
        candidates.append(
            HypothesisCandidate(
                hypothesis_code=spec.hypothesis_code,
                evaluation_status=status,
                confidence_score=score,
                rank=rank,
                supporting_evidence_codes=support_codes,
                contradicting_evidence_codes=contradict_codes,
                explanation=spec.explanation,
                logic_version=spec.logic_version,
                evaluated_at=timestamp,
            )
        )
    return tuple(candidates)


def _fingerprint_payload(
    evaluation: RuleEvaluationInput,
    dependencies: tuple[str, ...],
    observations: tuple[KPIObservation, ...],
    plan: _MeasurementPlan,
) -> dict[str, object]:
    relevant = [
        observation.as_dict()
        for observation in _selected_observations(
            observations,
            keys=plan.semantic_current,
            include_declared_quality=plan.current_quality,
            declared_kpis=evaluation.rule.declared_kpi_codes,
        )
    ]
    include_history = bool(plan.semantic_history or plan.history_quality)
    history = (
        [
            {
                "observations": [
                    observation.as_dict()
                    for observation in _selected_observations(
                        frame.observations,
                        keys=plan.semantic_history,
                        include_declared_quality=plan.history_quality,
                        declared_kpis=evaluation.rule.declared_kpi_codes,
                    )
                ]
            }
            for frame in evaluation.history
        ]
        if include_history
        else []
    )
    return {
        "scope": evaluation.scope.as_dict(),
        "rule_definition_id": evaluation.rule.rule_definition_id,
        "rule_version_number": evaluation.rule.version_number,
        "diagnostic_code": evaluation.rule.diagnostic_code,
        "condition_hash": evaluation.rule.condition_hash,
        "definition_hash": evaluation.rule.definition_hash,
        "window_start": evaluation.window_start,
        "window_end": evaluation.window_end,
        "dependencies": list(dependencies),
        "semantic_measurement_keys": list(plan.semantic_current),
        "observations": relevant,
        "history": history,
        "analytics_data_version": evaluation.analytics_data_version,
        "engine_version": evaluation.engine_version,
    }


def evaluate_rule(evaluation: RuleEvaluationInput) -> EvaluationResult:
    """Evaluate one exact governed rule snapshot without any infrastructure access."""

    try:
        validated = _validate_snapshot(evaluation)
        if isinstance(validated, EvaluationIssue):
            return _result(evaluation, state="failed", issue=validated)
        condition, controls, dependencies, plan = validated
        observation_issue = _validate_observations(evaluation)
        if observation_issue is not None:
            return _result(
                evaluation,
                state="skipped",
                dependencies=dependencies,
                observations=tuple(
                    sorted(evaluation.observations, key=lambda item: item.measurement_key)
                ),
                issue=observation_issue,
            )
        measurements, by_key, quality, coverage, lineage = _build_measurements(evaluation, plan)
        missing_keys = sorted(key for key in plan.required_current if key not in measurements)
        if missing_keys:
            return _result(
                evaluation,
                state="skipped",
                dependencies=dependencies,
                observations=tuple(
                    sorted(evaluation.observations, key=lambda item: item.measurement_key)
                ),
                issue=_issue("missing_kpi", f"missing required measurements: {missing_keys}"),
            )
        predicate, trace = _trace_condition(condition, measurements)
        ordered_observations = tuple(
            sorted(evaluation.observations, key=lambda item: item.measurement_key)
        )
        if quality < MIN_USABLE_DATA_QUALITY and not plan.quality_aware:
            return _result(
                evaluation,
                state="skipped",
                dependencies=dependencies,
                observations=ordered_observations,
                trace=trace,
                issue=_issue(
                    "insufficient_data_quality",
                    "average quality "
                    f"{_decimal_text(quality)} is below "
                    f"{_decimal_text(MIN_USABLE_DATA_QUALITY)}",
                ),
            )
        if predicate is None:
            return _result(
                evaluation,
                state="skipped",
                dependencies=dependencies,
                observations=ordered_observations,
                trace=trace,
                issue=_issue("condition_not_evaluable", "condition evaluation was indeterminate"),
            )
        if predicate is False:
            return _result(
                evaluation,
                state="not_matched",
                dependencies=dependencies,
                observations=ordered_observations,
                trace=trace,
            )
        evidence, evidence_issue = _build_evidence(evaluation.rule, by_key)
        if evidence_issue is not None:
            return _result(
                evaluation,
                state="skipped",
                dependencies=dependencies,
                observations=ordered_observations,
                trace=trace,
                issue=evidence_issue,
            )
        recommendations, action_issue = _build_recommendations(evaluation.rule)
        if action_issue is not None:
            return _result(
                evaluation,
                state="failed",
                dependencies=dependencies,
                observations=ordered_observations,
                trace=trace,
                issue=action_issue,
            )
        confidence = _confidence(
            quality=quality,
            coverage=coverage,
            lineage=lineage,
            evidence=evidence,
        )
        severity = _severity(evaluation.rule, controls, by_key)
        priority = _priority(severity, confidence, recommendations)
        primary = by_key.get(evaluation.rule.primary_kpi_code)
        primary_spec = next(
            (
                item
                for item in evaluation.rule.evidence
                if item.kpi_code == evaluation.rule.primary_kpi_code
            ),
            None,
        )
        reference = (
            None
            if primary_spec is None or primary_spec.reference_key is None
            else by_key.get(primary_spec.reference_key)
        )
        fingerprint = canonical_sha256(
            _fingerprint_payload(evaluation, dependencies, ordered_observations, plan)
        )
        diagnostic = DiagnosticCandidate(
            diagnostic_code=evaluation.rule.diagnostic_code,
            fingerprint=fingerprint,
            domain=evaluation.rule.domain,
            title=evaluation.rule.title,
            summary=evaluation.rule.summary,
            severity=severity,
            confidence_score=confidence,
            priority=priority,
            detected_at=evaluation.evaluated_at,
            affected_from=evaluation.window_start,
            affected_to=evaluation.window_end,
            primary_kpi_code=evaluation.rule.primary_kpi_code,
            observed_value=None if primary is None else primary.value,
            reference_value=None if reference is None else reference.value,
            value_unit=KPI_BY_CODE[evaluation.rule.primary_kpi_code].unit,
            analytics_data_version=evaluation.analytics_data_version,
            formula_version=1 if primary is None else primary.formula_version,
        )
        hypotheses = _build_hypotheses(
            evaluation.rule, evidence, confidence, evaluation.evaluated_at
        )
        return _result(
            evaluation,
            state="matched",
            dependencies=dependencies,
            observations=ordered_observations,
            trace=trace,
            diagnostic=diagnostic,
            evidence=evidence,
            hypotheses=hypotheses,
            recommendations=recommendations,
        )
    except (DiagnosticEngineValidationError, CanonicalizationError) as exc:
        return _result(
            evaluation,
            state="failed",
            issue=_issue("invalid_observation", str(exc)),
        )
    except Exception as exc:  # pragma: no cover - defensive boundary tested via monkeypatch
        return _result(
            evaluation,
            state="failed",
            issue=_issue("internal_evaluation_error", type(exc).__name__),
        )


__all__ = [
    "MIN_USABLE_DATA_QUALITY",
    "ActionRecommendationCandidate",
    "ActionReference",
    "CanonicalizationError",
    "DiagnosticCandidate",
    "DiagnosticEngineValidationError",
    "EvaluationIssue",
    "EvaluationResult",
    "EvaluationScope",
    "EvidenceCandidate",
    "EvidenceSpec",
    "HypothesisCandidate",
    "HypothesisSpec",
    "KPIObservation",
    "ObservationFrame",
    "RuleEvaluationInput",
    "RuleSnapshot",
    "TraceEntry",
    "canonical_json",
    "canonical_sha256",
    "evaluate_rule",
]
