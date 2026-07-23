"""Global deterministic validation for the governed diagnostic rule catalog."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from pharma_api.domain.analytics.kpis import KPI_BY_CODE, UNAVAILABLE_KPIS
from pharma_api.domain.diagnostics.actions import ACTION_BY_CODE
from pharma_api.domain.diagnostics.conditions import (
    ConditionValidationError,
    condition_kpi_dependencies,
    parse_condition,
    parse_rule_controls,
    serialize_condition,
    serialize_rule_controls,
)
from pharma_api.domain.diagnostics.engine_contracts import (
    DiagnosticEngineValidationError,
    canonical_sha256,
)
from pharma_api.domain.diagnostics.rules.definitions import GovernedRuleDefinition

_RULE_CODE_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_OWNER_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_-]{1,119}$")
_UNAVAILABLE_KPI_CODES: Final = frozenset(item.code for item in UNAVAILABLE_KPIS)
_FORBIDDEN_INFRASTRUCTURE_MARKERS: Final = (
    "pharma_api.infrastructure",
    "sqlalchemy",
    "fastapi",
    "dramatiq",
    "redis",
)


@dataclass(frozen=True, slots=True)
class RuleCatalogValidationError(ValueError):
    """Raised when one or more catalog invariants are violated."""

    errors: tuple[str, ...]

    def __str__(self) -> str:
        return "; ".join(self.errors)


def _text_error(
    errors: list[str],
    value: str,
    field: str,
    *,
    maximum: int,
) -> None:
    if not value or value != value.strip():
        errors.append(f"{field} must be non-empty and trimmed")
    elif len(value) > maximum:
        errors.append(f"{field} exceeds {maximum} characters")


def rule_validation_errors(rule: GovernedRuleDefinition) -> tuple[str, ...]:
    """Return all structural and cross-catalog errors for one rule."""

    errors: list[str] = []
    if _RULE_CODE_PATTERN.fullmatch(rule.code) is None:
        errors.append("code must be a stable two-segment code")
    if not rule.code.startswith(f"{rule.domain}."):
        errors.append("code prefix must match domain")
    if isinstance(rule.version, bool) or not isinstance(rule.version, int) or rule.version < 1:
        errors.append("version must be an integer >= 1")
    _text_error(errors, rule.title, "title", maximum=180)
    _text_error(errors, rule.objective, "objective", maximum=1_000)
    _text_error(errors, rule.summary, "summary", maximum=2_000)
    _text_error(errors, rule.evaluation_window, "evaluation_window", maximum=240)
    _text_error(errors, rule.expected_impact, "expected_impact", maximum=1_000)
    _text_error(errors, rule.change_note, "change_note", maximum=1_000)
    if _OWNER_PATTERN.fullmatch(rule.owner) is None:
        errors.append("owner must be a stable lowercase slug")
    if not rule.dimensions:
        errors.append("dimensions must not be empty")
    if len(rule.dimensions) != len(set(rule.dimensions)):
        errors.append("dimensions must be unique")
    if rule.status not in {"active", "deprecated"}:
        errors.append("unsupported lifecycle status")
    if not rule.actions:
        errors.append("at least one advisory action is required")
    if not rule.evidence:
        errors.append("at least one evidence specification is required")
    if not rule.hypotheses:
        errors.append("at least one explicitly probabilistic hypothesis is required")

    try:
        serialized_condition = serialize_condition(rule.condition)
        parsed_condition = parse_condition(serialized_condition)
        if serialize_condition(parsed_condition) != serialized_condition:
            errors.append("condition round-trip changed the canonical document")
    except ConditionValidationError as exc:
        errors.extend(f"invalid condition: {item}" for item in exc.errors)

    try:
        serialized_controls = serialize_rule_controls(rule.controls)
        parsed_controls = parse_rule_controls(serialized_controls)
        if serialize_rule_controls(parsed_controls) != serialized_controls:
            errors.append("controls round-trip changed the canonical document")
    except ConditionValidationError as exc:
        errors.extend(f"invalid controls: {item}" for item in exc.errors)

    dependencies = condition_kpi_dependencies(rule.condition)
    if dependencies != rule.declared_kpi_codes:
        errors.append("declared KPI dependencies differ from the DSL dependencies")
    if rule.primary_kpi_code not in dependencies:
        errors.append("primary KPI must be a condition dependency")
    if any(code not in KPI_BY_CODE for code in dependencies):
        errors.append("all dependencies must reference operational KPI definitions")
    if any(code in _UNAVAILABLE_KPI_CODES for code in dependencies):
        errors.append("unavailable KPIs are forbidden in active rule definitions")

    primary = KPI_BY_CODE.get(rule.primary_kpi_code)
    if primary is None:
        errors.append("primary KPI is unknown")
    else:
        unsupported_dimensions = set(rule.dimensions) - set(primary.dimensions)
        if unsupported_dimensions:
            errors.append(
                "dimensions are unsupported by the primary KPI: "
                + ", ".join(sorted(unsupported_dimensions))
            )

    action_codes = [reference.action_code for reference in rule.actions]
    if len(action_codes) != len(set(action_codes)):
        errors.append("action references must be unique")
    for reference in rule.actions:
        definition = ACTION_BY_CODE.get(reference.action_code)
        if definition is None:
            errors.append(f"unknown action {reference.action_code!r}")
            continue
        if definition.version != reference.action_version:
            errors.append(f"action {reference.action_code!r} uses a non-current version")
        if definition.domain != rule.domain:
            errors.append(f"action {reference.action_code!r} belongs to another domain")
        if definition.status != "active":
            errors.append(f"action {reference.action_code!r} is not active")
        action_payload = definition.as_dict()
        if action_payload["execution_mode"] != "human_review_required":
            errors.append(f"action {reference.action_code!r} is not advisory-only")
        if bool(action_payload["allows_automatic_financial_execution"]):
            errors.append(f"action {reference.action_code!r} permits financial automation")

    evidence_codes = [item.evidence_code for item in rule.evidence]
    if len(evidence_codes) != len(set(evidence_codes)):
        errors.append("evidence codes must be unique inside a rule")
    evidence_code_set = set(evidence_codes)
    for evidence in rule.evidence:
        if evidence.kpi_code not in dependencies:
            errors.append(f"evidence {evidence.evidence_code!r} uses an undeclared KPI")

    hypothesis_codes = [item.hypothesis_code for item in rule.hypotheses]
    if len(hypothesis_codes) != len(set(hypothesis_codes)):
        errors.append("hypothesis codes must be unique inside a rule")
    for hypothesis in rule.hypotheses:
        linked = set(hypothesis.supporting_evidence_codes + hypothesis.contradicting_evidence_codes)
        unknown = linked - evidence_code_set
        if unknown:
            errors.append(
                f"hypothesis {hypothesis.hypothesis_code!r} links unknown evidence: "
                + ", ".join(sorted(unknown))
            )
        explanation = hypothesis.explanation.casefold()
        if re.search(r"\b(?:pode|podem|may|might|could)\b", explanation) is None:
            errors.append(
                f"hypothesis {hypothesis.hypothesis_code!r} must use probabilistic language"
            )

    for limitation in rule.limitations:
        _text_error(errors, limitation, "limitation", maximum=1_000)
    if len(rule.limitations) != len(set(rule.limitations)):
        errors.append("limitations must be unique")

    try:
        snapshot = rule.to_snapshot()
        if snapshot.computed_condition_hash() != snapshot.condition_hash:
            errors.append("snapshot condition hash is inconsistent")
        if snapshot.computed_definition_hash() != snapshot.definition_hash:
            errors.append("snapshot definition hash is inconsistent")
        if snapshot.diagnostic_code != rule.code:
            errors.append("snapshot code differs from governed code")
    except DiagnosticEngineValidationError as exc:
        errors.append(f"invalid RuleSnapshot conversion: {exc}")

    return tuple(errors)


def validate_rule(rule: GovernedRuleDefinition) -> None:
    """Raise one deterministic aggregate error when a rule is invalid."""

    errors = rule_validation_errors(rule)
    if errors:
        raise RuleCatalogValidationError(tuple(f"{rule.code}: {item}" for item in errors))


def _freeze_manifest_value(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_manifest_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_manifest_value(item) for item in value)
    return value


def _freeze_manifest_mapping(value: dict[str, object]) -> Mapping[str, object]:
    return MappingProxyType({key: _freeze_manifest_value(item) for key, item in value.items()})


def catalog_manifest(
    rules: Sequence[GovernedRuleDefinition],
) -> tuple[Mapping[str, object], ...]:
    """Return the deeply immutable complete catalog manifest in input order."""

    return tuple(_freeze_manifest_mapping(rule.as_dict()) for rule in rules)


def catalog_hash(rules: Sequence[GovernedRuleDefinition]) -> str:
    """Return the global SHA-256 over every governed rule field."""

    return canonical_sha256(catalog_manifest(rules))


def validate_catalog(rules: Sequence[GovernedRuleDefinition]) -> None:
    """Validate ordering, identities, hashes and all rule-local invariants."""

    errors: list[str] = []
    if not rules:
        errors.append("catalog must not be empty")
    codes = [rule.code for rule in rules]
    if codes != sorted(codes):
        errors.append("catalog must use lexical code order")
    if len(codes) != len(set(codes)):
        errors.append("catalog contains duplicate rule codes")
    version_keys = [(rule.code, rule.version) for rule in rules]
    if len(version_keys) != len(set(version_keys)):
        errors.append("catalog contains duplicate rule versions")
    identities = [rule.rule_definition_id for rule in rules]
    if len(identities) != len(set(identities)):
        errors.append("catalog contains duplicate deterministic UUIDs")

    for rule in rules:
        errors.extend(f"{rule.code}: {item}" for item in rule_validation_errors(rule))

    definition_hashes = [rule.to_snapshot().definition_hash for rule in rules]
    if len(definition_hashes) != len(set(definition_hashes)):
        errors.append("catalog contains duplicate executable definition hashes")
    governance_hashes = [rule.governance_hash for rule in rules]
    if len(governance_hashes) != len(set(governance_hashes)):
        errors.append("catalog contains duplicate governance hashes")

    if errors:
        raise RuleCatalogValidationError(tuple(errors))


def read_only_rule_index(
    rules: Sequence[GovernedRuleDefinition],
) -> MappingProxyType[str, GovernedRuleDefinition]:
    """Build a read-only code index after full validation."""

    validate_catalog(rules)
    return MappingProxyType({rule.code: rule for rule in rules})


def forbidden_infrastructure_markers() -> tuple[str, ...]:
    """Expose the import-boundary markers used by architecture regression tests."""

    return _FORBIDDEN_INFRASTRUCTURE_MARKERS
