"""Governed deterministic production rules for the suppliers domain."""

from __future__ import annotations

from decimal import Decimal

from pharma_api.domain.diagnostics.actions import ACTION_BY_CODE
from pharma_api.domain.diagnostics.conditions import (
    AbsChange,
    AllOf,
    Compare,
    Condition,
    Fixed,
    Kpi,
    NetworkAverage,
    Persisted,
    Severity,
)
from pharma_api.domain.diagnostics.engine_contracts import (
    ActionReference,
    EvidenceDirection,
    EvidenceSpec,
    EvidenceType,
    HypothesisSpec,
)
from pharma_api.domain.diagnostics.rules.definitions import GovernedRuleDefinition

_OWNER = "supplier-management"
_COMMON_LIMITATIONS = (
    "The rule reports an observed analytical signal and does not prove root cause.",
    "Supplier, order, payment, credit or commercial decisions require authorized human review.",
)


def _action(code: str, rationale: str) -> ActionReference:
    definition = ACTION_BY_CODE[code]
    return ActionReference(
        action_code=definition.code,
        action_version=definition.version,
        rationale=rationale,
        suggested_priority=definition.default_priority,
    )


def _evidence(
    *,
    code: str,
    kpi: str,
    observation_key: str,
    evidence_type: EvidenceType,
    direction: EvidenceDirection,
    detail: str,
    reference_key: str | None = None,
) -> EvidenceSpec:
    return EvidenceSpec(
        evidence_code=code,
        evidence_type=evidence_type,
        kpi_code=kpi,
        observation_key=observation_key,
        reference_key=reference_key,
        direction=direction,
        relation="supports",
        weight=Decimal("1"),
        detail=detail,
    )


def _hypothesis(code: str, evidence_code: str, explanation: str) -> HypothesisSpec:
    return HypothesisSpec(
        hypothesis_code=code,
        explanation=explanation,
        supporting_evidence_codes=(evidence_code,),
        logic_version="suppliers-v1",
        minimum_support=Decimal("0.5000"),
    )


def _rule(
    *,
    code: str,
    title: str,
    objective: str,
    summary: str,
    severity: Severity,
    primary_kpi: str,
    condition: Condition,
    action_code: str,
    action_rationale: str,
    evidence_code: str,
    evidence_type: EvidenceType,
    evidence_direction: EvidenceDirection,
    evidence_detail: str,
    hypothesis_code: str,
    hypothesis: str,
    expected_impact: str,
    dimensions: tuple[str, ...],
    evaluation_window: str,
    observation_key: str | None = None,
    reference_key: str | None = None,
    limitations: tuple[str, ...] = _COMMON_LIMITATIONS,
) -> GovernedRuleDefinition:
    return GovernedRuleDefinition(
        code=code,
        version=1,
        title=title,
        objective=objective,
        summary=summary,
        domain="suppliers",
        base_severity=severity,
        primary_kpi_code=primary_kpi,
        condition=condition,
        actions=(_action(action_code, action_rationale),),
        evidence=(
            _evidence(
                code=evidence_code,
                kpi=primary_kpi,
                observation_key=observation_key or primary_kpi,
                evidence_type=evidence_type,
                direction=evidence_direction,
                detail=evidence_detail,
                reference_key=reference_key,
            ),
        ),
        hypotheses=(_hypothesis(hypothesis_code, evidence_code, hypothesis),),
        dimensions=dimensions,
        evaluation_window=evaluation_window,
        expected_impact=expected_impact,
        limitations=limitations,
        owner=_OWNER,
        change_note="Initial governed suppliers production rule.",
    )


_CURRENT_WINDOW = "current analytical period"
_PREVIOUS_WINDOW = "current analytical period versus the previous comparable period"
_NETWORK_WINDOW = "current analytical period versus the authorized network average"
_PERSISTENCE_WINDOW = "current analytical frame plus two previous frames"

SUPPLIERS_RULES: tuple[GovernedRuleDefinition, ...] = tuple(
    sorted(
        (
            _rule(
                code="suppliers.average_lead_time_above_network",
                title="Lead time acima da rede",
                objective="Comparar o lead time médio local à média governada da rede.",
                summary="O lead time médio supera a média da rede.",
                severity="high",
                primary_kpi="suppliers.average_lead_time",
                condition=Compare(
                    Kpi("suppliers.average_lead_time"),
                    "gt",
                    NetworkAverage("suppliers.average_lead_time"),
                ),
                action_code="suppliers.lead_time_review",
                action_rationale=(
                    "Revisar etapas e acordos sem modificar fornecedor automaticamente."
                ),
                evidence_code="suppliers.lead_time_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail="Lead time médio comparado à média autorizada da rede.",
                hypothesis_code="suppliers.local_lead_time_gap",
                hypothesis="Processo, rota ou condição do fornecedor podem explicar o desvio.",
                expected_impact="Direcionar revisão de prazo com decisão humana.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:suppliers.average_lead_time",
            ),
            _rule(
                code="suppliers.average_lead_time_increase",
                title="Aumento do lead time",
                objective=(
                    "Detectar aumento direcional do lead time médio frente ao período anterior."
                ),
                summary="O lead time médio aumentou no escopo avaliado.",
                severity="high",
                primary_kpi="suppliers.average_lead_time",
                condition=Compare(
                    AbsChange(
                        "suppliers.average_lead_time",
                        baseline="previous",
                    ),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="suppliers.lead_time_review",
                action_rationale=(
                    "Revisar trajetória e etapas antes de alterar qualquer relacionamento."
                ),
                evidence_code="suppliers.lead_time_increase_signal",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail="Lead time atual comparado ao período anterior equivalente.",
                hypothesis_code="suppliers.lead_time_deterioration",
                hypothesis="Rota, processo ou condição operacional podem explicar o aumento.",
                expected_impact="Conter deterioração de prazo com revisão rastreável.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:suppliers.average_lead_time",
            ),
            _rule(
                code="suppliers.average_minimum_order_increase",
                title="Aumento do pedido mínimo médio",
                objective="Detectar aumento direcional do pedido mínimo médio.",
                summary="O pedido mínimo médio aumentou no escopo avaliado.",
                severity="medium",
                primary_kpi="suppliers.average_minimum_order",
                condition=Compare(
                    AbsChange(
                        "suppliers.average_minimum_order",
                        baseline="previous",
                    ),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="suppliers.renegotiation",
                action_rationale="Revisar condição comercial sem aceitar compromisso financeiro.",
                evidence_code="suppliers.average_minimum_order_increase_signal",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail=(
                    "Pedido mínimo médio atual comparado ao período anterior equivalente."
                ),
                hypothesis_code="suppliers.minimum_order_pressure",
                hypothesis="Mudança de condição comercial ou mix pode explicar o aumento.",
                expected_impact="Apoiar renegociação sem emitir pedido.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:suppliers.average_minimum_order",
            ),
            _rule(
                code="suppliers.cost_variation_above_network",
                title="Variação de custo acima da rede",
                objective="Comparar a variação de custo à média governada da rede.",
                summary="A variação de custo supera a média da rede.",
                severity="high",
                primary_kpi="suppliers.cost_variation",
                condition=Compare(
                    Kpi("suppliers.cost_variation"),
                    "gt",
                    NetworkAverage("suppliers.cost_variation"),
                ),
                action_code="suppliers.renegotiation",
                action_rationale="Revisar composição e condição antes de qualquer negociação.",
                evidence_code="suppliers.cost_variation_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail="Variação de custo comparada à média autorizada da rede.",
                hypothesis_code="suppliers.local_cost_variation_gap",
                hypothesis="Mix ou condição comercial podem explicar o desvio.",
                expected_impact="Priorizar revisão de custo com evidência comparável.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:suppliers.cost_variation",
            ),
            _rule(
                code="suppliers.cost_variation_positive",
                title="Variação positiva de custo",
                objective="Detectar variação de custo acima da fronteira neutra de zero.",
                summary="Existe variação positiva de custo no escopo avaliado.",
                severity="high",
                primary_kpi="suppliers.cost_variation",
                condition=Compare(
                    Kpi("suppliers.cost_variation"),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="suppliers.renegotiation",
                action_rationale=(
                    "Analisar produtos e condições sem aceitar alteração automaticamente."
                ),
                evidence_code="suppliers.cost_variation_positive_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail="Variação de custo observada acima da fronteira neutra de zero.",
                hypothesis_code="suppliers.cost_increase_context",
                hypothesis="Mix ou condição comercial podem estar associados à variação positiva.",
                expected_impact="Dar visibilidade à pressão de custo sem presumir causa.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_CURRENT_WINDOW,
            ),
            _rule(
                code="suppliers.dependency_above_network",
                title="Dependência de fornecedor acima da rede",
                objective=(
                    "Comparar a dependência do principal fornecedor à média governada da rede."
                ),
                summary="A dependência do principal fornecedor supera a média da rede.",
                severity="medium",
                primary_kpi="suppliers.dependency",
                condition=Compare(
                    Kpi("suppliers.dependency"),
                    "gt",
                    NetworkAverage("suppliers.dependency"),
                ),
                action_code="suppliers.dependency_reduction",
                action_rationale=(
                    "Revisar alternativas sem remover ou substituir fornecedor automaticamente."
                ),
                evidence_code="suppliers.dependency_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail="Dependência local comparada à média autorizada da rede.",
                hypothesis_code="suppliers.local_dependency_concentration",
                hypothesis="Sortimento ou disponibilidade de alternativas podem explicar o desvio.",
                expected_impact="Reduzir exposição mediante decisão humana.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:suppliers.dependency",
            ),
            _rule(
                code="suppliers.failure_rate_increase",
                title="Aumento da taxa de falhas do fornecedor",
                objective="Detectar aumento direcional da taxa de falhas.",
                summary="A taxa de falhas aumentou no escopo avaliado.",
                severity="high",
                primary_kpi="suppliers.failure_rate",
                condition=Compare(
                    AbsChange(
                        "suppliers.failure_rate",
                        baseline="previous",
                    ),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="suppliers.quality_claim",
                action_rationale=(
                    "Organizar evidências e revisão sem declarar infração automaticamente."
                ),
                evidence_code="suppliers.failure_rate_increase_signal",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail="Taxa de falhas atual comparada ao período anterior equivalente.",
                hypothesis_code="suppliers.failure_process_deterioration",
                hypothesis="Qualidade, documentação ou atendimento podem explicar o aumento.",
                expected_impact="Conter deterioração com tratamento rastreável.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:suppliers.failure_rate",
            ),
            _rule(
                code="suppliers.failure_rate_persistent_positive",
                title="Falhas recorrentes do fornecedor",
                objective="Detectar falhas positivas no frame atual e em dois frames anteriores.",
                summary="Falhas permanecem presentes no período atual e no histórico exigido.",
                severity="high",
                primary_kpi="suppliers.failure_rate",
                condition=AllOf(
                    nodes=(
                        Compare(
                            Kpi("suppliers.failure_rate"),
                            "gt",
                            Fixed(Decimal("0")),
                        ),
                        Persisted(
                            Compare(
                                Kpi("suppliers.failure_rate"),
                                "gt",
                                Fixed(Decimal("0")),
                            ),
                            periods=2,
                        ),
                    ),
                ),
                action_code="suppliers.quality_claim",
                action_rationale=(
                    "Escalar revisão da recorrência sem penalizar ou modificar fornecedor "
                    "automaticamente."
                ),
                evidence_code="suppliers.failure_rate_persistent_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail=(
                    "Taxa atual positiva; persistência histórica comprovada pelo trace."
                ),
                hypothesis_code="suppliers.unresolved_quality_constraint",
                hypothesis=(
                    "Restrição de qualidade ou atendimento ainda não resolvida pode explicar a "
                    "recorrência."
                ),
                expected_impact="Distinguir recorrência de evento isolado.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_PERSISTENCE_WINDOW,
            ),
            _rule(
                code="suppliers.failure_rate_positive",
                title="Ocorrência de falha do fornecedor",
                objective="Detectar taxa de falhas acima da fronteira objetiva de zero.",
                summary="Existe falha registrada no escopo avaliado.",
                severity="medium",
                primary_kpi="suppliers.failure_rate",
                condition=Compare(
                    Kpi("suppliers.failure_rate"),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="suppliers.quality_claim",
                action_rationale="Classificar evidências sem presumir falha contratual.",
                evidence_code="suppliers.failure_rate_positive_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail="Taxa de falhas observada acima de zero.",
                hypothesis_code="suppliers.failure_event_context",
                hypothesis=(
                    "Qualidade, documentação ou atendimento podem estar associados ao evento."
                ),
                expected_impact="Dar visibilidade ao evento sem atribuir causa.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_CURRENT_WINDOW,
            ),
            _rule(
                code="suppliers.fill_rate_below_network",
                title="Fill rate abaixo da rede",
                objective="Comparar o fill rate local à média governada da rede.",
                summary="O fill rate está abaixo da média da rede.",
                severity="high",
                primary_kpi="suppliers.fill_rate",
                condition=Compare(
                    Kpi("suppliers.fill_rate"),
                    "lt",
                    NetworkAverage("suppliers.fill_rate"),
                ),
                action_code="suppliers.fill_rate_action",
                action_rationale="Preparar plano de acompanhamento sem transmitir pedido.",
                evidence_code="suppliers.fill_rate_network_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail="Fill rate local comparado à média autorizada da rede.",
                hypothesis_code="suppliers.local_fill_rate_gap",
                hypothesis="Disponibilidade, programação ou atendimento podem explicar o desvio.",
                expected_impact="Direcionar acompanhamento de atendimento.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:suppliers.fill_rate",
            ),
            _rule(
                code="suppliers.fill_rate_decline",
                title="Queda do fill rate",
                objective="Detectar queda direcional do fill rate frente ao período anterior.",
                summary="O fill rate caiu no escopo avaliado.",
                severity="high",
                primary_kpi="suppliers.fill_rate",
                condition=Compare(
                    AbsChange(
                        "suppliers.fill_rate",
                        baseline="previous",
                    ),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="suppliers.fill_rate_action",
                action_rationale="Acompanhar atendimento sem alterar pedidos automaticamente.",
                evidence_code="suppliers.fill_rate_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail="Fill rate atual comparado ao período anterior equivalente.",
                hypothesis_code="suppliers.fill_rate_deterioration",
                hypothesis="Disponibilidade ou programação pode explicar a queda.",
                expected_impact="Conter deterioração de atendimento.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:suppliers.fill_rate",
            ),
            _rule(
                code="suppliers.on_time_rate_below_network",
                title="Pontualidade abaixo da rede",
                objective="Comparar a pontualidade local à média governada da rede.",
                summary="A taxa de entregas no prazo está abaixo da média da rede.",
                severity="high",
                primary_kpi="suppliers.on_time_rate",
                condition=Compare(
                    Kpi("suppliers.on_time_rate"),
                    "lt",
                    NetworkAverage("suppliers.on_time_rate"),
                ),
                action_code="suppliers.lead_time_review",
                action_rationale=(
                    "Revisar etapas e compromissos sem alterar fornecedor automaticamente."
                ),
                evidence_code="suppliers.on_time_rate_network_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail="Pontualidade comparada à média autorizada da rede.",
                hypothesis_code="suppliers.local_on_time_gap",
                hypothesis="Rota, programação ou processo podem explicar o desvio.",
                expected_impact="Direcionar revisão de prazo e entrega.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:suppliers.on_time_rate",
            ),
            _rule(
                code="suppliers.on_time_rate_decline",
                title="Queda da pontualidade",
                objective="Detectar queda direcional da taxa de entregas no prazo.",
                summary="A pontualidade caiu no escopo avaliado.",
                severity="high",
                primary_kpi="suppliers.on_time_rate",
                condition=Compare(
                    AbsChange(
                        "suppliers.on_time_rate",
                        baseline="previous",
                    ),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="suppliers.lead_time_review",
                action_rationale=(
                    "Revisar trajetória e ocorrências sem assumir descumprimento contratual."
                ),
                evidence_code="suppliers.on_time_rate_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail="Pontualidade atual comparada ao período anterior equivalente.",
                hypothesis_code="suppliers.on_time_deterioration",
                hypothesis="Rota, programação ou processo podem explicar a queda.",
                expected_impact="Conter deterioração da pontualidade.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:suppliers.on_time_rate",
            ),
            _rule(
                code="suppliers.quality_score_below_network",
                title="Qualidade abaixo da rede",
                objective="Comparar o score de qualidade à média governada da rede.",
                summary="O score de qualidade está abaixo da média da rede.",
                severity="high",
                primary_kpi="suppliers.quality_score",
                condition=Compare(
                    Kpi("suppliers.quality_score"),
                    "lt",
                    NetworkAverage("suppliers.quality_score"),
                ),
                action_code="suppliers.quality_claim",
                action_rationale="Organizar evidências e revisão humana do desvio.",
                evidence_code="suppliers.quality_score_network_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail="Score de qualidade comparado à média autorizada da rede.",
                hypothesis_code="suppliers.local_quality_gap",
                hypothesis="Produto, documentação ou atendimento podem explicar o desvio.",
                expected_impact="Priorizar revisão de qualidade com rastreabilidade.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:suppliers.quality_score",
            ),
            _rule(
                code="suppliers.quality_score_decline",
                title="Queda do score de qualidade",
                objective="Detectar queda direcional do score de qualidade.",
                summary="O score de qualidade caiu no escopo avaliado.",
                severity="high",
                primary_kpi="suppliers.quality_score",
                condition=Compare(
                    AbsChange(
                        "suppliers.quality_score",
                        baseline="previous",
                    ),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="suppliers.quality_claim",
                action_rationale="Revisar evidências antes de qualquer reclamação formal.",
                evidence_code="suppliers.quality_score_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail=(
                    "Score de qualidade atual comparado ao período anterior equivalente."
                ),
                hypothesis_code="suppliers.quality_deterioration",
                hypothesis="Produto, documentação ou atendimento podem explicar a queda.",
                expected_impact="Conter deterioração de qualidade sem decisão automática.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:suppliers.quality_score",
            ),
            _rule(
                code="suppliers.return_rate_above_network",
                title="Devoluções acima da rede",
                objective="Comparar a taxa de devolução à média governada da rede.",
                summary="A taxa de devolução supera a média da rede.",
                severity="high",
                primary_kpi="suppliers.return_rate",
                condition=Compare(
                    Kpi("suppliers.return_rate"),
                    "gt",
                    NetworkAverage("suppliers.return_rate"),
                ),
                action_code="suppliers.quality_claim",
                action_rationale="Revisar evidências e produtos sem executar crédito ou baixa.",
                evidence_code="suppliers.return_rate_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail="Taxa de devolução comparada à média autorizada da rede.",
                hypothesis_code="suppliers.local_return_gap",
                hypothesis="Qualidade, divergência ou processo podem explicar o desvio.",
                expected_impact="Direcionar revisão de devoluções.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:suppliers.return_rate",
            ),
            _rule(
                code="suppliers.return_rate_increase",
                title="Aumento da taxa de devolução",
                objective="Detectar aumento direcional da taxa de devolução.",
                summary="A taxa de devolução aumentou no escopo avaliado.",
                severity="high",
                primary_kpi="suppliers.return_rate",
                condition=Compare(
                    AbsChange(
                        "suppliers.return_rate",
                        baseline="previous",
                    ),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="suppliers.quality_claim",
                action_rationale="Revisar evidências sem executar crédito ou baixa.",
                evidence_code="suppliers.return_rate_increase_signal",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail=(
                    "Taxa de devolução atual comparada ao período anterior equivalente."
                ),
                hypothesis_code="suppliers.return_deterioration",
                hypothesis="Qualidade, divergência ou processo podem explicar o aumento.",
                expected_impact="Conter deterioração de devoluções.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:suppliers.return_rate",
            ),
            _rule(
                code="suppliers.stockout_association_above_network",
                title="Associação com ruptura acima da rede",
                objective="Comparar a associação observada com ruptura à média da rede.",
                summary=(
                    "A associação com ruptura supera a média da rede; isso não prova causalidade."
                ),
                severity="high",
                primary_kpi="suppliers.stockout_association",
                condition=Compare(
                    Kpi("suppliers.stockout_association"),
                    "gt",
                    NetworkAverage("suppliers.stockout_association"),
                ),
                action_code="suppliers.fill_rate_action",
                action_rationale=(
                    "Revisar atendimento e disponibilidade sem atribuir causa automaticamente."
                ),
                evidence_code="suppliers.stockout_association_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail="Associação observada comparada à média autorizada da rede.",
                hypothesis_code="suppliers.stockout_association_context",
                hypothesis="Atendimento, demanda ou disponibilidade podem explicar a associação.",
                expected_impact="Direcionar análise sem declarar causalidade.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:suppliers.stockout_association",
            ),
            _rule(
                code="suppliers.stockout_association_positive",
                title="Associação observada com ruptura",
                objective="Detectar associação positiva entre produtos do fornecedor e ruptura.",
                summary="Existe associação observada com ruptura; isso não prova causalidade.",
                severity="medium",
                primary_kpi="suppliers.stockout_association",
                condition=Compare(
                    Kpi("suppliers.stockout_association"),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="suppliers.fill_rate_action",
                action_rationale="Revisar atendimento e disponibilidade sem atribuir causa.",
                evidence_code="suppliers.stockout_association_positive_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail="Associação observada acima da fronteira de zero.",
                hypothesis_code="suppliers.stockout_association_context_positive",
                hypothesis=(
                    "Atendimento, demanda ou disponibilidade podem estar associados ao sinal."
                ),
                expected_impact="Dar visibilidade à associação sem tratá-la como causa.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_CURRENT_WINDOW,
            ),
            _rule(
                code="suppliers.top5_concentration_above_network",
                title="Concentração nos cinco maiores fornecedores acima da rede",
                objective="Comparar a concentração top 5 à média governada da rede.",
                summary="A concentração nos cinco maiores fornecedores supera a média da rede.",
                severity="medium",
                primary_kpi="suppliers.top5_concentration",
                condition=Compare(
                    Kpi("suppliers.top5_concentration"),
                    "gt",
                    NetworkAverage("suppliers.top5_concentration"),
                ),
                action_code="suppliers.dependency_reduction",
                action_rationale=(
                    "Avaliar alternativas sem substituir fornecedores automaticamente."
                ),
                evidence_code="suppliers.top5_concentration_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail="Concentração top 5 comparada à média autorizada da rede.",
                hypothesis_code="suppliers.supplier_portfolio_concentration",
                hypothesis=(
                    "Sortimento ou disponibilidade de alternativas podem explicar a concentração."
                ),
                expected_impact="Reduzir exposição com decisão humana.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:suppliers.top5_concentration",
            ),
        ),
        key=lambda rule: rule.code,
    )
)
