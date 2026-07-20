"""Governed immutable definitions for deterministic diagnostic rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pharma_api.domain.diagnostics.conditions import (
    DEFAULT_RULE_CONTROLS,
    Condition,
    RuleControls,
    Severity,
    condition_kpi_dependencies,
    serialize_condition,
    serialize_rule_controls,
)
from pharma_api.domain.diagnostics.engine_contracts import (
    ActionReference,
    EvidenceSpec,
    HypothesisSpec,
    RuleSnapshot,
    canonical_sha256,
)

RuleDomain = Literal["inventory", "sales", "margin", "purchases", "suppliers", "operations"]
RuleLifecycleStatus = Literal["active", "deprecated"]

_RULE_UUID_PREFIX = "pharma-intelligence:diagnostic-rule"


def deterministic_rule_id(code: str) -> UUID:
    """Return the stable UUIDv5 identity for a system rule definition."""

    return uuid5(NAMESPACE_URL, f"{_RULE_UUID_PREFIX}:{code}")


@dataclass(frozen=True, slots=True)
class GovernedRuleDefinition:
    """Versioned rule metadata that converts to the engine's public snapshot contract.

    Governance-only fields remain in this code catalog until a later persistence block
    defines a lossless synchronizer.  The executable representation is always the
    existing :class:`RuleSnapshot`; this class does not introduce a competing DSL or
    evaluation model.
    """

    code: str
    version: int
    title: str
    objective: str
    summary: str
    domain: RuleDomain
    base_severity: Severity
    primary_kpi_code: str
    condition: Condition
    actions: tuple[ActionReference, ...]
    evidence: tuple[EvidenceSpec, ...]
    hypotheses: tuple[HypothesisSpec, ...]
    dimensions: tuple[str, ...]
    evaluation_window: str
    expected_impact: str
    limitations: tuple[str, ...]
    owner: str
    change_note: str
    controls: RuleControls = DEFAULT_RULE_CONTROLS
    status: RuleLifecycleStatus = "active"

    @property
    def rule_definition_id(self) -> UUID:
        return deterministic_rule_id(self.code)

    @property
    def declared_kpi_codes(self) -> tuple[str, ...]:
        """Return the exact condition dependencies in stable lexical order."""

        return condition_kpi_dependencies(self.condition)

    def to_snapshot(self) -> RuleSnapshot:
        """Create the canonical engine-facing snapshot without infrastructure access."""

        return RuleSnapshot.from_documents(
            rule_definition_id=self.rule_definition_id,
            version_number=self.version,
            ownership_type="system",
            rule_tenant_id=None,
            diagnostic_code=self.code,
            domain=self.domain,
            title=self.title,
            summary=self.summary,
            base_severity=self.base_severity,
            primary_kpi_code=self.primary_kpi_code,
            condition_document=serialize_condition(self.condition),
            declared_kpi_codes=self.declared_kpi_codes,
            controls_document=serialize_rule_controls(self.controls),
            actions=self.actions,
            evidence=self.evidence,
            hypotheses=self.hypotheses,
        )

    def as_dict(self) -> dict[str, object]:
        """Return the complete governance manifest with deterministic field order."""

        snapshot = self.to_snapshot()
        return {
            "rule_definition_id": self.rule_definition_id,
            "code": self.code,
            "version": self.version,
            "title": self.title,
            "objective": self.objective,
            "summary": self.summary,
            "domain": self.domain,
            "base_severity": self.base_severity,
            "primary_kpi_code": self.primary_kpi_code,
            "condition": serialize_condition(self.condition),
            "declared_kpi_codes": list(self.declared_kpi_codes),
            "controls": serialize_rule_controls(self.controls),
            "actions": [action.as_dict() for action in self.actions],
            "evidence": [item.as_dict() for item in self.evidence],
            "hypotheses": [item.as_dict() for item in self.hypotheses],
            "dimensions": list(self.dimensions),
            "evaluation_window": self.evaluation_window,
            "expected_impact": self.expected_impact,
            "limitations": list(self.limitations),
            "owner": self.owner,
            "change_note": self.change_note,
            "status": self.status,
            "condition_hash": snapshot.condition_hash,
            "definition_hash": snapshot.definition_hash,
        }

    @property
    def governance_hash(self) -> str:
        """Hash every executable and governance field in the code catalog entry."""

        return canonical_sha256(self.as_dict())
