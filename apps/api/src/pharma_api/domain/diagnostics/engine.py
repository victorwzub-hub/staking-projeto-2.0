"""Pure deterministic evaluation core for governed diagnostic rules."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from typing import cast

from pharma_api.domain.analytics.kpis import KPI_BY_CODE
from pharma_api.domain.diagnostics.actions import ACTION_BY_CODE, ActionDefinition
from pharma_api.domain.diagnostics.conditions import (
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
    evaluate_operand,
    evaluate_predicate,
    parse_condition,
    parse_rule_controls,
    serialize_condition,
)
from pharma_api.domain.diagnostics.engine_contracts import (
    _ENGINE_DECIMAL_CONTEXT,
    _SEVERITY_PRIORITY,
    _SEVERITY_RANK,
    MIN_USABLE_DATA_QUALITY,
    SHA256_PATTERN,
    ActionRecommendationCandidate,
    ActionReference,
    CanonicalizationError,
    ConfidenceBreakdown,
    DiagnosticCandidate,
    DiagnosticEngineValidationError,
    EvaluationIssue,
    EvaluationResult,
    EvaluationScope,
    EvidenceCandidate,
    EvidenceSpec,
    HypothesisCandidate,
    HypothesisSpec,
    HypothesisStatus,
    KPIObservation,
    ObservationFrame,
    PriorityBreakdown,
    RuleEvaluationInput,
    RuleSnapshot,
    TraceEntry,
    TraceOutcome,
    _decimal_text,
    _issue,
    _quantize_score,
    _result,
    canonical_json,
    canonical_sha256,
)


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
                required_current.add(f"coverage:{node.kpi_code}")
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
    measurements["_frame_period_start"] = frame.period_start
    measurements["_frame_period_end"] = frame.period_end
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


def _resolved_operand(operand: Operand, measurements: Mapping[str, object]) -> dict[str, object]:
    return {
        "operand": operand.as_json(),
        "value": evaluate_operand(operand, measurements),
    }


def _resolved_condition_values(
    condition: Condition, measurements: Mapping[str, object]
) -> dict[str, object]:
    frame_context = {
        key.removeprefix("_"): measurements[key]
        for key in ("_frame_period_start", "_frame_period_end")
        if key in measurements
    }
    if isinstance(condition, Compare):
        return {
            **frame_context,
            "left": _resolved_operand(condition.left, measurements),
            "operator": condition.op,
            "right": _resolved_operand(condition.right, measurements),
        }
    if isinstance(condition, Between):
        return {
            **frame_context,
            "value": _resolved_operand(condition.value, measurements),
            "minimum": _resolved_operand(condition.minimum, measurements),
            "maximum": _resolved_operand(condition.maximum, measurements),
        }
    if isinstance(condition, DataAvailable):
        key = f"coverage:{condition.kpi_code}"
        return {
            **frame_context,
            "measurement_key": key,
            "coverage": measurements.get(key),
            "minimum_coverage": condition.min_coverage,
        }
    if isinstance(condition, MinQuality):
        return {
            **frame_context,
            "measurement_key": "quality_score",
            "quality_score": measurements.get("quality_score"),
            "minimum_quality": condition.score,
        }
    if isinstance(condition, MissingData):
        return {
            **frame_context,
            "measurement_key": condition.kpi_code,
            "value": measurements.get(condition.kpi_code),
        }
    if isinstance(condition, Persisted):
        history = measurements.get("history")
        return {
            "required_periods": condition.periods,
            "available_periods": len(history) if isinstance(history, list) else 0,
        }
    return frame_context


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
            resolved_values_json=canonical_json(
                _resolved_condition_values(condition, measurements)
            ),
        )
    ]
    if isinstance(condition, (AllOf, AnyOf)):
        for index, child in enumerate(condition.nodes):
            _, child_entries = _trace_condition(child, measurements, f"{path}.nodes[{index}]")
            entries.extend(child_entries)
    elif isinstance(condition, Negate):
        _, child_entries = _trace_condition(condition.node, measurements, f"{path}.node")
        entries.extend(child_entries)
    elif isinstance(condition, Persisted):
        history = measurements.get("history")
        if isinstance(history, list):
            selected = history[-condition.periods :]
            start_index = len(history) - len(selected)
            for offset, frame in enumerate(selected):
                if not isinstance(frame, Mapping):
                    continue
                _, child_entries = _trace_condition(
                    condition.predicate,
                    cast(Mapping[str, object], frame),
                    f"{path}.history[{start_index + offset}].predicate",
                )
                entries.extend(child_entries)
    return value, tuple(entries)


def _missing_measurement_keys(
    required_keys: tuple[str, ...], measurements: Mapping[str, object]
) -> tuple[str, ...]:
    return tuple(
        sorted(
            key for key in required_keys if key not in measurements or measurements.get(key) is None
        )
    )


def _measurement_completeness(
    required_keys: tuple[str, ...], measurements: Mapping[str, object]
) -> Decimal:
    if not required_keys:
        return Decimal("1")
    available = len(required_keys) - len(_missing_measurement_keys(required_keys, measurements))
    return Decimal(available) / Decimal(len(required_keys))


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
    plan: _MeasurementPlan,
) -> EvaluationIssue | None:
    formula_versions: dict[str, set[int]] = {}
    current_observations = _selected_observations(
        evaluation.observations,
        keys=plan.semantic_current,
        include_declared_quality=plan.current_quality,
        declared_kpis=evaluation.rule.declared_kpi_codes,
    )
    for observation in current_observations:
        formula_versions.setdefault(observation.kpi_code, set()).add(observation.formula_version)
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
        history_observations = _selected_observations(
            frame.observations,
            keys=plan.semantic_history,
            include_declared_quality=plan.history_quality,
            declared_kpis=evaluation.rule.declared_kpi_codes,
        )
        for observation in history_observations:
            formula_versions.setdefault(observation.kpi_code, set()).add(
                observation.formula_version
            )
            if observation.data_version != evaluation.analytics_data_version:
                return _issue("data_version_mismatch", "history observation data version differs")
            if observation.period_end >= evaluation.window_start:
                return _issue(
                    "window_mismatch",
                    "history observations must end before the evaluation window",
                )
    mismatched_formula_versions = {
        kpi_code: sorted(versions)
        for kpi_code, versions in sorted(formula_versions.items())
        if len(versions) > 1
    }
    if mismatched_formula_versions:
        return _issue(
            "formula_version_mismatch",
            f"observations use inconsistent KPI formula versions: {mismatched_formula_versions}",
        )
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
        if reference is not None and reference.kpi_code != spec.kpi_code:
            return (), _issue(
                "invalid_rule_snapshot",
                f"evidence {spec.evidence_code!r} compares observations from different KPIs",
            )
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
    measurement_completeness: Decimal,
    evidence: tuple[EvidenceCandidate, ...],
) -> ConfidenceBreakdown:
    """Calculate an explicit bounded score using only governed deterministic weights.

    Quality contributes 55%, coverage 20%, lineage availability 15%, and the
    factual support ratio 10%. The three data components are multiplied by the
    required-measurement completeness ratio before weighting. Contradicting
    evidence then subtracts up to 25%. Consequently missing or poor data can
    never increase confidence.
    """

    support = sum((item.weight for item in evidence if item.relation == "supports"), Decimal("0"))
    contradiction = sum(
        (item.weight for item in evidence if item.relation == "contradicts"), Decimal("0")
    )
    total = support + contradiction
    support_ratio = Decimal("0") if total == 0 else support / total
    contradiction_penalty = min(Decimal("0.25"), contradiction * Decimal("0.10"))
    effective_quality = quality * measurement_completeness
    effective_coverage = coverage * measurement_completeness
    effective_lineage = lineage * measurement_completeness
    raw = (
        effective_quality * Decimal("0.55")
        + effective_coverage * Decimal("0.20")
        + effective_lineage * Decimal("0.15")
        + support_ratio * Decimal("0.10")
        - contradiction_penalty
    )
    return ConfidenceBreakdown(
        quality_score=quality,
        coverage_score=coverage,
        lineage_score=lineage,
        measurement_completeness=measurement_completeness,
        support_weight=support,
        contradiction_weight=contradiction,
        support_ratio=support_ratio,
        contradiction_penalty=contradiction_penalty,
        raw_score=raw,
        final_score=_quantize_score(raw),
    )


def _severity(
    rule: RuleSnapshot,
    controls: RuleControls,
    by_key: Mapping[str, KPIObservation],
) -> Severity:
    if not controls.severity_ladder:
        return rule.base_severity
    reference_spec = next(
        (
            item
            for item in rule.evidence
            if item.kpi_code == rule.primary_kpi_code and item.reference_key is not None
        ),
        None,
    )
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
        if (
            deviation >= step.threshold_pct
            and _SEVERITY_RANK[step.severity] > _SEVERITY_RANK[selected]
        ):
            selected = step.severity
    return selected


def _priority(
    severity: Severity,
    confidence: Decimal,
    actions: tuple[ActionRecommendationCandidate, ...],
) -> PriorityBreakdown:
    """Combine severity, governed action impact and confidence into priority 1..4."""

    severity_priority = _SEVERITY_PRIORITY[severity]
    impact_priority = min((item.suggested_priority for item in actions), default=4)
    base = min(severity_priority, impact_priority)
    confidence_adjustment = 0
    if confidence < Decimal("0.5000"):
        confidence_adjustment = 1
    elif confidence >= Decimal("0.8500"):
        confidence_adjustment = -1
    final_priority = max(1, min(4, base + confidence_adjustment))
    return PriorityBreakdown(
        severity=severity,
        severity_priority=severity_priority,
        action_priority=impact_priority,
        confidence_adjustment=confidence_adjustment,
        final_priority=final_priority,
    )


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
                "period_start": frame.period_start,
                "period_end": frame.period_end,
                "observations": [
                    observation.as_dict()
                    for observation in _selected_observations(
                        frame.observations,
                        keys=plan.semantic_history,
                        include_declared_quality=plan.history_quality,
                        declared_kpis=evaluation.rule.declared_kpi_codes,
                    )
                ],
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
        "semantic_history_measurement_keys": list(plan.semantic_history),
        "observations": relevant,
        "history": history,
        "analytics_data_version": evaluation.analytics_data_version,
        "engine_version": evaluation.engine_version,
    }


def _evaluate_rule(evaluation: RuleEvaluationInput) -> EvaluationResult:
    try:
        validated = _validate_snapshot(evaluation)
        if isinstance(validated, EvaluationIssue):
            return _result(evaluation, state="failed", issue=validated)
        condition, controls, dependencies, plan = validated
        observation_issue = _validate_observations(evaluation, plan)
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
        predicate, trace = _trace_condition(condition, measurements)
        ordered_observations = tuple(
            sorted(evaluation.observations, key=lambda item: item.measurement_key)
        )
        missing_keys = _missing_measurement_keys(plan.required_current, measurements)
        completeness = _measurement_completeness(plan.required_current, measurements)
        effective_quality = quality * completeness
        if predicate is None and missing_keys:
            return _result(
                evaluation,
                state="skipped",
                dependencies=dependencies,
                observations=ordered_observations,
                trace=trace,
                issue=_issue("missing_kpi", f"missing required measurements: {list(missing_keys)}"),
            )
        if effective_quality < MIN_USABLE_DATA_QUALITY and not plan.quality_aware:
            return _result(
                evaluation,
                state="skipped",
                dependencies=dependencies,
                observations=ordered_observations,
                trace=trace,
                issue=_issue(
                    "insufficient_data_quality",
                    "effective quality "
                    f"{_decimal_text(effective_quality)} is below "
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
                state=("failed" if evidence_issue.code == "invalid_rule_snapshot" else "skipped"),
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
            measurement_completeness=completeness,
            evidence=evidence,
        )
        severity = _severity(evaluation.rule, controls, by_key)
        priority = _priority(severity, confidence.final_score, recommendations)
        primary = by_key.get(evaluation.rule.primary_kpi_code)
        primary_reference_spec = next(
            (
                item
                for item in evaluation.rule.evidence
                if item.kpi_code == evaluation.rule.primary_kpi_code
                and item.reference_key is not None
            ),
            None,
        )
        reference = (
            None
            if primary_reference_spec is None
            else by_key.get(cast(str, primary_reference_spec.reference_key))
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
            confidence_score=confidence.final_score,
            priority=priority.final_priority,
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
            evaluation.rule, evidence, confidence.final_score, evaluation.evaluated_at
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
            confidence_breakdown=confidence,
            priority_breakdown=priority,
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


def evaluate_rule(evaluation: RuleEvaluationInput) -> EvaluationResult:
    """Evaluate one exact governed rule snapshot under a fixed decimal context."""

    with localcontext(_ENGINE_DECIMAL_CONTEXT):
        return _evaluate_rule(evaluation)


__all__ = [
    "MIN_USABLE_DATA_QUALITY",
    "ActionRecommendationCandidate",
    "ActionReference",
    "CanonicalizationError",
    "ConfidenceBreakdown",
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
    "PriorityBreakdown",
    "RuleEvaluationInput",
    "RuleSnapshot",
    "TraceEntry",
    "canonical_json",
    "canonical_sha256",
    "evaluate_rule",
]
