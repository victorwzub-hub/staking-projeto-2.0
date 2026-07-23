"""Governed deterministic production rules for the purchases domain."""

from __future__ import annotations

from decimal import Decimal

from pharma_api.domain.diagnostics.actions import ACTION_BY_CODE
from pharma_api.domain.diagnostics.conditions import (
    AbsChange,
    AllOf,
    CategoryAverage,
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

_OWNER = "purchasing-operations"
_COMMON_LIMITATIONS = (
    "The rule reports an observed analytical signal and does not prove root cause.",
    "Any order, payment, credit, receipt or parameter change requires authorized human review.",
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
        logic_version="purchases-v1",
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
        domain="purchases",
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
        change_note="Initial governed purchases production rule.",
    )


_CURRENT_WINDOW = "current analytical period"
_PREVIOUS_WINDOW = "current analytical period versus the previous comparable period"
_NETWORK_WINDOW = "current analytical period versus the authorized network average"
_CATEGORY_WINDOW = "current analytical period versus the authorized category average"
_PERSISTENCE_WINDOW = "current analytical frame plus two previous frames"

PURCHASES_RULES: tuple[GovernedRuleDefinition, ...] = tuple(
    sorted(
        (
            _rule(
                code="purchases.average_unit_cost_above_network",
                title="Custo unitário médio acima da rede",
                objective="Comparar o custo unitário médio local à média governada da rede.",
                summary="O custo unitário médio supera a média da rede no mesmo contexto.",
                severity="high",
                primary_kpi="purchases.average_unit_cost",
                condition=Compare(
                    Kpi("purchases.average_unit_cost"),
                    "gt",
                    NetworkAverage("purchases.average_unit_cost"),
                ),
                action_code="purchases.order_parameter_review",
                action_rationale=(
                    "Revisar composição, fornecedor e parâmetros antes de preparar qualquer pedido."
                ),
                evidence_code="purchases.average_unit_cost_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail="Custo unitário médio local comparado à média autorizada da rede.",
                hypothesis_code="purchases.local_cost_composition_gap",
                hypothesis=(
                    "Mix, fornecedor ou condição comercial podem explicar o desvio observado."
                ),
                expected_impact=(
                    "Direcionar revisão de custo sem emitir ou alterar pedidos automaticamente."
                ),
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:purchases.average_unit_cost",
            ),
            _rule(
                code="purchases.average_unit_cost_increase",
                title="Aumento do custo unitário médio",
                objective=(
                    "Detectar aumento direcional do custo unitário médio frente ao período "
                    "anterior."
                ),
                summary="O custo unitário médio aumentou no escopo avaliado.",
                severity="high",
                primary_kpi="purchases.average_unit_cost",
                condition=Compare(
                    AbsChange(
                        "purchases.average_unit_cost",
                        baseline="previous",
                    ),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="purchases.order_parameter_review",
                action_rationale=(
                    "Decompor custo, mix e fornecedor antes de revisar parâmetros de compra."
                ),
                evidence_code="purchases.average_unit_cost_increase_signal",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail=(
                    "Custo unitário médio atual comparado ao período anterior equivalente."
                ),
                hypothesis_code="purchases.unit_cost_pressure",
                hypothesis=(
                    "Mudança de mix, fornecedor ou condição negociada pode estar associada ao "
                    "aumento."
                ),
                expected_impact="Conter deterioração de custo com decisão humana rastreável.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:purchases.average_unit_cost",
            ),
            _rule(
                code="purchases.cancellation_rate_above_network",
                title="Cancelamentos de compra acima da rede",
                objective=(
                    "Comparar a taxa local de cancelamento de compras à média governada da rede."
                ),
                summary="A taxa de cancelamento de compras supera a média da rede.",
                severity="high",
                primary_kpi="purchases.cancellation_rate",
                condition=Compare(
                    Kpi("purchases.cancellation_rate"),
                    "gt",
                    NetworkAverage("purchases.cancellation_rate"),
                ),
                action_code="purchases.order_parameter_review",
                action_rationale=(
                    "Revisar motivos, parâmetros e fluxo de aprovação no escopo com desvio."
                ),
                evidence_code="purchases.cancellation_rate_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail="Taxa local de cancelamento comparada à média autorizada da rede.",
                hypothesis_code="purchases.local_cancellation_process_gap",
                hypothesis=(
                    "Parâmetros, aprovação ou disponibilidade podem explicar o desvio local."
                ),
                expected_impact=(
                    "Reduzir cancelamentos evitáveis sem emitir ou cancelar pedidos "
                    "automaticamente."
                ),
                dimensions=("branch", "supplier", "category"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:purchases.cancellation_rate",
            ),
            _rule(
                code="purchases.cancellation_rate_increase",
                title="Aumento da taxa de cancelamento de compras",
                objective=(
                    "Detectar aumento direcional da taxa de cancelamento frente ao período "
                    "anterior."
                ),
                summary="A taxa de cancelamento de compras aumentou no escopo avaliado.",
                severity="high",
                primary_kpi="purchases.cancellation_rate",
                condition=Compare(
                    AbsChange(
                        "purchases.cancellation_rate",
                        baseline="previous",
                    ),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="purchases.order_parameter_review",
                action_rationale=(
                    "Investigar motivos e parâmetros antes que a deterioração persista."
                ),
                evidence_code="purchases.cancellation_rate_increase_signal",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail=(
                    "Taxa de cancelamento atual comparada ao período anterior equivalente."
                ),
                hypothesis_code="purchases.cancellation_process_deterioration",
                hypothesis=(
                    "Mudança de parâmetros, aprovação ou disponibilidade pode explicar o aumento."
                ),
                expected_impact="Conter deterioração do processo com revisão autorizada.",
                dimensions=("branch", "supplier", "category"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:purchases.cancellation_rate",
            ),
            _rule(
                code="purchases.discount_rate_below_network",
                title="Desconto obtido abaixo da rede",
                objective="Comparar a taxa de desconto obtida à média governada da rede.",
                summary="A taxa de desconto obtida está abaixo da média da rede.",
                severity="medium",
                primary_kpi="purchases.discount_rate",
                condition=Compare(
                    Kpi("purchases.discount_rate"),
                    "lt",
                    NetworkAverage("purchases.discount_rate"),
                ),
                action_code="purchases.order_parameter_review",
                action_rationale=(
                    "Revisar composição e condições comerciais antes de qualquer novo pedido."
                ),
                evidence_code="purchases.discount_rate_network_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail=(
                    "Taxa local de desconto obtida comparada à média autorizada da rede."
                ),
                hypothesis_code="purchases.local_discount_condition_gap",
                hypothesis=(
                    "Mix, fornecedor ou condição negociada podem explicar o desvio observado."
                ),
                expected_impact="Apoiar revisão de condições sem assumir compromisso financeiro.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:purchases.discount_rate",
            ),
            _rule(
                code="purchases.discount_rate_decline",
                title="Queda da taxa de desconto obtida",
                objective=(
                    "Detectar queda direcional da taxa de desconto obtida frente ao período "
                    "anterior."
                ),
                summary="A taxa de desconto obtida caiu no escopo avaliado.",
                severity="medium",
                primary_kpi="purchases.discount_rate",
                condition=Compare(
                    AbsChange(
                        "purchases.discount_rate",
                        baseline="previous",
                    ),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="purchases.order_parameter_review",
                action_rationale=(
                    "Revisar mix e condições negociadas antes de preparar nova compra."
                ),
                evidence_code="purchases.discount_rate_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail="Taxa de desconto atual comparada ao período anterior equivalente.",
                hypothesis_code="purchases.discount_condition_erosion",
                hypothesis=(
                    "Mudança de mix ou condição negociada pode estar associada à queda observada."
                ),
                expected_impact="Preservar condições comerciais com revisão humana.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:purchases.discount_rate",
            ),
            _rule(
                code="purchases.emergency_rate_increase",
                title="Aumento de compras emergenciais",
                objective="Detectar aumento direcional da taxa de compras emergenciais.",
                summary="A taxa de compras emergenciais aumentou no escopo avaliado.",
                severity="high",
                primary_kpi="purchases.emergency_rate",
                condition=Compare(
                    AbsChange(
                        "purchases.emergency_rate",
                        baseline="previous",
                    ),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="purchases.emergency_rate_reduction",
                action_rationale=(
                    "Revisar causas operacionais e parâmetros sem emitir pedidos automaticamente."
                ),
                evidence_code="purchases.emergency_rate_increase_signal",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail=(
                    "Taxa de compras emergenciais atual comparada ao período anterior equivalente."
                ),
                hypothesis_code="purchases.emergency_demand_or_parameter_gap",
                hypothesis=(
                    "Demanda recente, ruptura ou parâmetro inadequado podem explicar o aumento."
                ),
                expected_impact="Reduzir recorrência emergencial com ação consultiva.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:purchases.emergency_rate",
            ),
            _rule(
                code="purchases.emergency_rate_persistent_positive",
                title="Compras emergenciais recorrentes",
                objective=(
                    "Detectar taxa positiva de compras emergenciais no frame atual e em dois "
                    "frames anteriores."
                ),
                summary=(
                    "Compras emergenciais permanecem presentes no período atual e no histórico "
                    "exigido."
                ),
                severity="high",
                primary_kpi="purchases.emergency_rate",
                condition=AllOf(
                    nodes=(
                        Compare(
                            Kpi("purchases.emergency_rate"),
                            "gt",
                            Fixed(Decimal("0")),
                        ),
                        Persisted(
                            Compare(
                                Kpi("purchases.emergency_rate"),
                                "gt",
                                Fixed(Decimal("0")),
                            ),
                            periods=2,
                        ),
                    ),
                ),
                action_code="purchases.emergency_rate_reduction",
                action_rationale="Escalar revisão da recorrência sem emitir ou transmitir pedido.",
                evidence_code="purchases.emergency_rate_persistent_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail=(
                    "Taxa atual positiva; a persistência nos dois frames anteriores é "
                    "comprovada pelo trace."
                ),
                hypothesis_code="purchases.unresolved_emergency_constraint",
                hypothesis=(
                    "Restrição ainda não resolvida de cobertura, demanda ou processo pode "
                    "explicar a recorrência."
                ),
                expected_impact="Distinguir evento isolado de recorrência operacional.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_PERSISTENCE_WINDOW,
            ),
            _rule(
                code="purchases.freight_rate_above_network",
                title="Taxa de frete acima da rede",
                objective="Comparar a taxa local de frete à média governada da rede.",
                summary="A taxa de frete supera a média da rede no mesmo contexto.",
                severity="medium",
                primary_kpi="purchases.freight_rate",
                condition=Compare(
                    Kpi("purchases.freight_rate"),
                    "gt",
                    NetworkAverage("purchases.freight_rate"),
                ),
                action_code="purchases.freight_review",
                action_rationale=(
                    "Revisar condições logísticas sem contratar ou alterar frete automaticamente."
                ),
                evidence_code="purchases.freight_rate_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail="Taxa local de frete comparada à média autorizada da rede.",
                hypothesis_code="purchases.local_freight_condition_gap",
                hypothesis=(
                    "Rota, fornecedor, volume ou condição negociada podem explicar o desvio."
                ),
                expected_impact="Direcionar revisão logística com rastreabilidade.",
                dimensions=("branch", "supplier", "category"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:purchases.freight_rate",
            ),
            _rule(
                code="purchases.freight_rate_increase",
                title="Aumento da taxa de frete",
                objective=(
                    "Detectar aumento direcional da taxa de frete frente ao período anterior."
                ),
                summary="A taxa de frete aumentou no escopo avaliado.",
                severity="medium",
                primary_kpi="purchases.freight_rate",
                condition=Compare(
                    AbsChange(
                        "purchases.freight_rate",
                        baseline="previous",
                    ),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="purchases.freight_review",
                action_rationale=(
                    "Revisar rotas, volumes e condições antes de qualquer contratação."
                ),
                evidence_code="purchases.freight_rate_increase_signal",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail="Taxa de frete atual comparada ao período anterior equivalente.",
                hypothesis_code="purchases.freight_rate_pressure",
                hypothesis="Rota, volume ou condição negociada pode estar associada ao aumento.",
                expected_impact="Conter deterioração logística sem compromisso automático.",
                dimensions=("branch", "supplier", "category"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:purchases.freight_rate",
            ),
            _rule(
                code="purchases.freight_value_increase",
                title="Aumento do valor de frete",
                objective=(
                    "Detectar aumento direcional do valor de frete frente ao período anterior."
                ),
                summary="O valor de frete aumentou no escopo avaliado.",
                severity="medium",
                primary_kpi="purchases.freight_value",
                condition=Compare(
                    AbsChange(
                        "purchases.freight_value",
                        baseline="previous",
                    ),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="purchases.freight_review",
                action_rationale=(
                    "Decompor valor, volume e taxa antes de revisar condições logísticas."
                ),
                evidence_code="purchases.freight_value_increase_signal",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail="Valor de frete atual comparado ao período anterior equivalente.",
                hypothesis_code="purchases.freight_value_composition_shift",
                hypothesis="Volume, rota ou taxa podem explicar o aumento observado.",
                expected_impact="Separar efeito de volume de deterioração logística.",
                dimensions=("branch", "supplier", "category"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:purchases.freight_value",
            ),
            _rule(
                code="purchases.multiple_adherence_below_network",
                title="Aderência ao múltiplo abaixo da rede",
                objective="Comparar a aderência local ao múltiplo à média governada da rede.",
                summary="A aderência ao múltiplo está abaixo da média da rede.",
                severity="medium",
                primary_kpi="purchases.multiple_adherence",
                condition=Compare(
                    Kpi("purchases.multiple_adherence"),
                    "lt",
                    NetworkAverage("purchases.multiple_adherence"),
                ),
                action_code="purchases.order_parameter_review",
                action_rationale=(
                    "Revisar cadastro e parâmetros sem modificar pedidos automaticamente."
                ),
                evidence_code="purchases.multiple_adherence_network_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail="Aderência local ao múltiplo comparada à média autorizada da rede.",
                hypothesis_code="purchases.local_multiple_parameter_gap",
                hypothesis="Cadastro, múltiplo ou processo local podem explicar o desvio.",
                expected_impact="Melhorar aderência com revisão controlada de parâmetros.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:purchases.multiple_adherence",
            ),
            _rule(
                code="purchases.multiple_adherence_decline",
                title="Queda da aderência ao múltiplo",
                objective=(
                    "Detectar queda direcional da aderência ao múltiplo frente ao período anterior."
                ),
                summary="A aderência ao múltiplo caiu no escopo avaliado.",
                severity="medium",
                primary_kpi="purchases.multiple_adherence",
                condition=Compare(
                    AbsChange(
                        "purchases.multiple_adherence",
                        baseline="previous",
                    ),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="purchases.order_parameter_review",
                action_rationale="Revisar cadastro e processo antes de alterar parâmetros.",
                evidence_code="purchases.multiple_adherence_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail=(
                    "Aderência atual ao múltiplo comparada ao período anterior equivalente."
                ),
                hypothesis_code="purchases.multiple_adherence_deterioration",
                hypothesis="Mudança de cadastro, fornecedor ou processo pode explicar a queda.",
                expected_impact="Conter deterioração de aderência sem automação de pedidos.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:purchases.multiple_adherence",
            ),
            _rule(
                code="purchases.receipt_fill_rate_below_category",
                title="Atendimento de quantidade abaixo da categoria",
                objective=(
                    "Comparar a taxa de atendimento de quantidade à média governada da categoria."
                ),
                summary="A taxa de atendimento de quantidade está abaixo da média da categoria.",
                severity="high",
                primary_kpi="purchases.receipt_fill_rate",
                condition=Compare(
                    Kpi("purchases.receipt_fill_rate"),
                    "lt",
                    CategoryAverage("purchases.receipt_fill_rate"),
                ),
                action_code="purchases.receipt_followup",
                action_rationale="Priorizar acompanhamento do recebimento com desvio relativo.",
                evidence_code="purchases.receipt_fill_rate_category_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail="Taxa de atendimento comparada à média autorizada da categoria.",
                hypothesis_code="purchases.category_receipt_constraint",
                hypothesis="Disponibilidade, fornecedor ou programação podem explicar o desvio.",
                expected_impact=(
                    "Melhorar atendimento sem aceitar ou alterar pedido automaticamente."
                ),
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_CATEGORY_WINDOW,
                reference_key="category_average:purchases.receipt_fill_rate",
            ),
            _rule(
                code="purchases.receipt_fill_rate_decline",
                title="Queda do atendimento de quantidade",
                objective="Detectar queda direcional da taxa de atendimento de quantidade.",
                summary="A taxa de atendimento de quantidade caiu no escopo avaliado.",
                severity="high",
                primary_kpi="purchases.receipt_fill_rate",
                condition=Compare(
                    AbsChange(
                        "purchases.receipt_fill_rate",
                        baseline="previous",
                    ),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="purchases.receipt_followup",
                action_rationale="Acompanhar pedidos e divergências antes que a queda persista.",
                evidence_code="purchases.receipt_fill_rate_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail=(
                    "Taxa de atendimento atual comparada ao período anterior equivalente."
                ),
                hypothesis_code="purchases.receipt_quantity_deterioration",
                hypothesis="Disponibilidade, fornecedor ou programação pode explicar a queda.",
                expected_impact="Conter deterioração de atendimento com acompanhamento humano.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:purchases.receipt_fill_rate",
            ),
            _rule(
                code="purchases.receipt_rate_below_network",
                title="Taxa de recebimento abaixo da rede",
                objective="Comparar a taxa local de recebimento à média governada da rede.",
                summary="A taxa de recebimento está abaixo da média da rede.",
                severity="high",
                primary_kpi="purchases.receipt_rate",
                condition=Compare(
                    Kpi("purchases.receipt_rate"),
                    "lt",
                    NetworkAverage("purchases.receipt_rate"),
                ),
                action_code="purchases.receipt_followup",
                action_rationale=(
                    "Priorizar cobrança e conferência dos pedidos com desvio relativo."
                ),
                evidence_code="purchases.receipt_rate_network_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail="Taxa local de recebimento comparada à média autorizada da rede.",
                hypothesis_code="purchases.local_receipt_process_gap",
                hypothesis="Programação, fornecedor ou conferência local podem explicar o desvio.",
                expected_impact=(
                    "Direcionar acompanhamento sem aceitar recebimentos automaticamente."
                ),
                dimensions=("branch", "supplier", "category"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:purchases.receipt_rate",
            ),
            _rule(
                code="purchases.receipt_rate_decline",
                title="Queda da taxa de recebimento",
                objective=(
                    "Detectar queda direcional da taxa de recebimento frente ao período anterior."
                ),
                summary="A taxa de recebimento caiu no escopo avaliado.",
                severity="high",
                primary_kpi="purchases.receipt_rate",
                condition=Compare(
                    AbsChange(
                        "purchases.receipt_rate",
                        baseline="previous",
                    ),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="purchases.receipt_followup",
                action_rationale=(
                    "Acompanhar pedidos pendentes sem confirmar ou modificar recebimentos."
                ),
                evidence_code="purchases.receipt_rate_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail=(
                    "Taxa de recebimento atual comparada ao período anterior equivalente."
                ),
                hypothesis_code="purchases.receipt_process_deterioration",
                hypothesis=(
                    "Programação, fornecedor ou conferência pode explicar a queda observada."
                ),
                expected_impact="Conter deterioração de recebimento com ação rastreável.",
                dimensions=("branch", "supplier", "category"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:purchases.receipt_rate",
            ),
            _rule(
                code="purchases.return_rate_above_network",
                title="Devoluções a fornecedores acima da rede",
                objective="Comparar a taxa local de devolução à média governada da rede.",
                summary="A taxa de devolução a fornecedores supera a média da rede.",
                severity="high",
                primary_kpi="purchases.return_rate",
                condition=Compare(
                    Kpi("purchases.return_rate"),
                    "gt",
                    NetworkAverage("purchases.return_rate"),
                ),
                action_code="purchases.return_process_review",
                action_rationale="Revisar motivos e produtos no escopo com desvio relativo.",
                evidence_code="purchases.return_rate_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail="Taxa local de devolução comparada à média autorizada da rede.",
                hypothesis_code="purchases.local_return_process_gap",
                hypothesis="Qualidade, divergência ou processo local podem explicar o desvio.",
                expected_impact="Reduzir devoluções evitáveis sem executar baixa ou crédito.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:purchases.return_rate",
            ),
            _rule(
                code="purchases.return_rate_increase",
                title="Aumento da taxa de devolução a fornecedores",
                objective=(
                    "Detectar aumento direcional da taxa de devolução frente ao período anterior."
                ),
                summary="A taxa de devolução a fornecedores aumentou no escopo avaliado.",
                severity="high",
                primary_kpi="purchases.return_rate",
                condition=Compare(
                    AbsChange(
                        "purchases.return_rate",
                        baseline="previous",
                    ),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="purchases.return_process_review",
                action_rationale=(
                    "Investigar produtos e motivos antes de qualquer baixa ou crédito."
                ),
                evidence_code="purchases.return_rate_increase_signal",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail=(
                    "Taxa de devolução atual comparada ao período anterior equivalente."
                ),
                hypothesis_code="purchases.return_process_deterioration",
                hypothesis="Qualidade, divergência ou processo podem explicar o aumento.",
                expected_impact="Conter deterioração de devoluções com revisão humana.",
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:purchases.return_rate",
            ),
            _rule(
                code="purchases.return_rate_positive",
                title="Ocorrência de devolução a fornecedores",
                objective="Detectar taxa positiva de devolução como evento operacional objetivo.",
                summary="Existe devolução a fornecedor no escopo avaliado.",
                severity="medium",
                primary_kpi="purchases.return_rate",
                condition=Compare(
                    Kpi("purchases.return_rate"),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="purchases.return_process_review",
                action_rationale=(
                    "Classificar motivos e conferir documentos sem executar baixa ou crédito."
                ),
                evidence_code="purchases.return_rate_positive_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail="Taxa observada de devolução acima da fronteira objetiva de zero.",
                hypothesis_code="purchases.return_event_context",
                hypothesis="Qualidade, divergência ou processo podem estar associados ao evento.",
                expected_impact=(
                    "Dar visibilidade ao evento sem presumir causa ou executar decisão financeira."
                ),
                dimensions=("branch", "supplier", "category", "product"),
                evaluation_window=_CURRENT_WINDOW,
            ),
        ),
        key=lambda rule: rule.code,
    )
)
