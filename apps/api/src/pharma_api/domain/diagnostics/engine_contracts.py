"""Immutable contracts and canonical primitives for diagnostic evaluation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Context, Decimal
from hashlib import sha256
from itertools import pairwise
from typing import Literal
from uuid import UUID

from pharma_api.domain.analytics.kpis import KPI_BY_CODE
from pharma_api.domain.diagnostics.conditions import (
    MAX_ABS_NUMBER,
    MAX_DECIMAL_PLACES,
    MAX_PERIODS,
    MIN_PERIODS,
    Severity,
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
    "formula_version_mismatch",
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
MAX_CANONICAL_DECIMAL_CHARACTERS = 256
MAX_STABLE_CODE_LENGTH = 140
MAX_TITLE_LENGTH = 180
MAX_SUMMARY_LENGTH = 2_000
MAX_METADATA_TEXT_LENGTH = 1_000
MAX_LINEAGE_REF_LENGTH = 500
MAX_LOGIC_VERSION_LENGTH = 40
MAX_RULE_ACTIONS = 16
MAX_RULE_EVIDENCE = 32
MAX_RULE_HYPOTHESES = 16
_ENGINE_DECIMAL_CONTEXT = Context(prec=38, rounding=ROUND_HALF_UP)

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

_SEVERITY_RANK: Mapping[Severity, int] = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
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
    text = format(value, "f")
    if len(text) > MAX_CANONICAL_DECIMAL_CHARACTERS:
        raise CanonicalizationError(
            "Decimal canonical form exceeds the bounded representation size"
        )
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


def _require_trimmed_text(value: str, field: str, *, max_length: int) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise DiagnosticEngineValidationError(f"{field} must be a trimmed non-empty string")
    if len(value) > max_length:
        raise DiagnosticEngineValidationError(f"{field} exceeds {max_length} characters")


def _require_stable_code(value: str, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) > MAX_STABLE_CODE_LENGTH
        or STABLE_CODE_PATTERN.fullmatch(value) is None
    ):
        raise DiagnosticEngineValidationError(f"invalid {field} format")


def _require_bounded_decimal(value: Decimal, field: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise DiagnosticEngineValidationError(f"{field} must be a finite Decimal")
    if abs(value) > MAX_ABS_NUMBER:
        raise DiagnosticEngineValidationError(
            f"{field} must have an absolute value <= {MAX_ABS_NUMBER}"
        )
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -MAX_DECIMAL_PLACES:
        raise DiagnosticEngineValidationError(
            f"{field} must have at most {MAX_DECIMAL_PLACES} decimal places"
        )


def _require_decimal_range(value: Decimal, field: str) -> None:
    _require_bounded_decimal(value, field)
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
        if self.value is not None:
            _require_bounded_decimal(self.value, "observation value")
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
        if self.lineage_ref is not None:
            _require_trimmed_text(
                self.lineage_ref,
                "lineage_ref",
                max_length=MAX_LINEAGE_REF_LENGTH,
            )
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
            if not isinstance(self.parameter, Decimal):
                raise DiagnosticEngineValidationError("percentile parameter must be a Decimal")
            _require_bounded_decimal(self.parameter, "percentile parameter")
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
        if not self.observations:
            raise DiagnosticEngineValidationError("history frames must not be empty")
        keys = [observation.measurement_key for observation in self.observations]
        if len(keys) != len(set(keys)):
            raise DiagnosticEngineValidationError(
                "history frame contains duplicate measurement keys"
            )

    @property
    def period_start(self) -> datetime:
        return min(observation.period_start for observation in self.observations)

    @property
    def period_end(self) -> datetime:
        return max(observation.period_end for observation in self.observations)

    def as_dict(self) -> dict[str, object]:
        return {
            "period_start": self.period_start,
            "period_end": self.period_end,
            "observations": [observation.as_dict() for observation in self.observations],
        }


@dataclass(frozen=True, slots=True)
class ActionReference:
    action_code: str
    action_version: int
    rationale: str
    suggested_priority: int | None = None

    def __post_init__(self) -> None:
        _require_stable_code(self.action_code, "action code")
        if (
            isinstance(self.action_version, bool)
            or not isinstance(self.action_version, int)
            or self.action_version < 1
        ):
            raise DiagnosticEngineValidationError("action_version must be >= 1")
        _require_trimmed_text(
            self.rationale,
            "action rationale",
            max_length=MAX_METADATA_TEXT_LENGTH,
        )
        if self.suggested_priority is not None and (
            isinstance(self.suggested_priority, bool)
            or not isinstance(self.suggested_priority, int)
            or self.suggested_priority not in {1, 2, 3, 4}
        ):
            raise DiagnosticEngineValidationError(
                "suggested_priority must be an integer between 1 and 4"
            )

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
        _require_stable_code(self.evidence_code, "evidence code")
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
        _require_trimmed_text(
            self.detail,
            "evidence detail",
            max_length=MAX_METADATA_TEXT_LENGTH,
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
        _require_stable_code(self.hypothesis_code, "hypothesis code")
        _require_trimmed_text(
            self.explanation,
            "hypothesis explanation",
            max_length=MAX_METADATA_TEXT_LENGTH,
        )
        _require_trimmed_text(
            self.logic_version,
            "logic_version",
            max_length=MAX_LOGIC_VERSION_LENGTH,
        )
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
        _require_stable_code(self.diagnostic_code, "diagnostic code")
        if self.domain not in _DIAGNOSTIC_DOMAINS:
            raise DiagnosticEngineValidationError("unsupported diagnostic domain")
        if self.base_severity not in {"info", "low", "medium", "high", "critical"}:
            raise DiagnosticEngineValidationError("unsupported base severity")
        if self.primary_kpi_code not in KPI_BY_CODE:
            raise DiagnosticEngineValidationError("unknown primary KPI")
        _require_trimmed_text(self.title, "title", max_length=MAX_TITLE_LENGTH)
        _require_trimmed_text(self.summary, "summary", max_length=MAX_SUMMARY_LENGTH)
        if len(self.declared_kpi_codes) != len(set(self.declared_kpi_codes)):
            raise DiagnosticEngineValidationError("declared KPI codes must be unique")
        if self.declared_kpi_codes != tuple(sorted(self.declared_kpi_codes)):
            raise DiagnosticEngineValidationError("declared KPI codes must use lexical order")
        if len(self.actions) > MAX_RULE_ACTIONS:
            raise DiagnosticEngineValidationError(
                f"rule actions exceed the maximum of {MAX_RULE_ACTIONS}"
            )
        if len(self.evidence) > MAX_RULE_EVIDENCE:
            raise DiagnosticEngineValidationError(
                f"rule evidence exceeds the maximum of {MAX_RULE_EVIDENCE}"
            )
        if len(self.hypotheses) > MAX_RULE_HYPOTHESES:
            raise DiagnosticEngineValidationError(
                f"rule hypotheses exceed the maximum of {MAX_RULE_HYPOTHESES}"
            )

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
        for previous, current in pairwise(self.history):
            if current.period_start <= previous.period_end:
                raise DiagnosticEngineValidationError(
                    "history frames must be strictly chronological and non-overlapping"
                )


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
    resolved_values_json: str = "{}"

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "node_type": self.node_type,
            "outcome": self.outcome,
            "condition": json.loads(self.condition_json),
            "resolved_values": json.loads(self.resolved_values_json),
        }


@dataclass(frozen=True, slots=True)
class ConfidenceBreakdown:
    quality_score: Decimal
    coverage_score: Decimal
    lineage_score: Decimal
    measurement_completeness: Decimal
    support_weight: Decimal
    contradiction_weight: Decimal
    support_ratio: Decimal
    contradiction_penalty: Decimal
    raw_score: Decimal
    final_score: Decimal
    formula_version: str = "1"

    def as_dict(self) -> dict[str, object]:
        return {
            "quality_score": self.quality_score,
            "coverage_score": self.coverage_score,
            "lineage_score": self.lineage_score,
            "measurement_completeness": self.measurement_completeness,
            "support_weight": self.support_weight,
            "contradiction_weight": self.contradiction_weight,
            "support_ratio": self.support_ratio,
            "contradiction_penalty": self.contradiction_penalty,
            "raw_score": self.raw_score,
            "final_score": self.final_score,
            "formula_version": self.formula_version,
        }


@dataclass(frozen=True, slots=True)
class PriorityBreakdown:
    severity: Severity
    severity_priority: int
    action_priority: int
    confidence_adjustment: int
    final_priority: int
    formula_version: str = "1"

    def as_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "severity_priority": self.severity_priority,
            "action_priority": self.action_priority,
            "confidence_adjustment": self.confidence_adjustment,
            "final_priority": self.final_priority,
            "formula_version": self.formula_version,
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
    confidence_breakdown: ConfidenceBreakdown | None = None
    priority_breakdown: PriorityBreakdown | None = None
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
            "confidence_breakdown": (
                None if self.confidence_breakdown is None else self.confidence_breakdown.as_dict()
            ),
            "priority_breakdown": (
                None if self.priority_breakdown is None else self.priority_breakdown.as_dict()
            ),
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
    confidence_breakdown: ConfidenceBreakdown | None = None,
    priority_breakdown: PriorityBreakdown | None = None,
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
            confidence_breakdown=confidence_breakdown,
            priority_breakdown=priority_breakdown,
            issue=issue,
        )
    )


def _issue(code: ErrorCode, message: str) -> EvaluationIssue:
    return EvaluationIssue(code=code, message=message)
