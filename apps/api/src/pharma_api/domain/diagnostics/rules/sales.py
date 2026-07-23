"""Governed deterministic production rules for the sales domain."""

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
    Trend,
)
from pharma_api.domain.diagnostics.engine_contracts import (
    ActionReference,
    EvidenceDirection,
    EvidenceSpec,
    EvidenceType,
    HypothesisSpec,
)
from pharma_api.domain.diagnostics.rules.definitions import GovernedRuleDefinition

_OWNER = "sales-operations"
_COMMON_LIMITATIONS = (
    "The rule reports an observed analytical signal and does not prove root cause.",
    "Commercial, staffing or financial intervention requires authorized human review.",
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
        logic_version="sales-v1",
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
        domain="sales",
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
        change_note="Initial governed sales production rule.",
    )


_PREVIOUS_WINDOW = "current analytical period versus the previous comparable period"
_NETWORK_WINDOW = "current analytical period versus the authorized network average"
_CATEGORY_WINDOW = "current analytical period versus the authorized category average"

SALES_RULES: tuple[GovernedRuleDefinition, ...] = tuple(
    sorted(
        (
            _rule(
                code="sales.active_product_count_decline",
                title="Queda de produtos ativos vendidos",
                objective=(
                    "Detectar redução do número de produtos vendidos frente ao período anterior."
                ),
                summary="A quantidade de produtos com venda caiu no escopo avaliado.",
                severity="medium",
                primary_kpi="sales.active_product_count",
                condition=Compare(
                    AbsChange("sales.active_product_count", baseline="previous"),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="sales.ticket_mix_review",
                action_rationale=(
                    "Revisar perda de amplitude do mix antes de definir ação comercial."
                ),
                evidence_code="sales.active_product_count_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail="Produtos vendidos comparados ao período anterior equivalente.",
                hypothesis_code="sales.assortment_demand_contraction",
                hypothesis=(
                    "Ruptura, menor demanda ou menor exposição do sortimento pode explicar "
                    "parte da redução."
                ),
                expected_impact="Recuperar amplitude do mix com decisão comercial rastreável.",
                dimensions=("branch", "category"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:sales.active_product_count",
            ),
            _rule(
                code="sales.average_discount_increase",
                title="Aumento do desconto médio",
                objective=(
                    "Detectar crescimento do desconto médio por venda frente ao período anterior."
                ),
                summary="O desconto médio por venda aumentou no escopo avaliado.",
                severity="medium",
                primary_kpi="sales.average_discount",
                condition=Compare(
                    AbsChange("sales.average_discount", baseline="previous"),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="sales.ticket_mix_review",
                action_rationale=(
                    "Revisar mix e uso de descontos sem alterar preços automaticamente."
                ),
                evidence_code="sales.average_discount_growth",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail="Desconto médio atual comparado ao período anterior equivalente.",
                hypothesis_code="sales.discount_dependency",
                hypothesis=(
                    "Mudança de mix, campanha ou prática operacional pode explicar o aumento "
                    "do desconto médio."
                ),
                expected_impact="Conter dependência de desconto preservando revisão humana.",
                dimensions=("branch", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:sales.average_discount",
            ),
            _rule(
                code="sales.average_ticket_below_network",
                title="Ticket médio abaixo da rede",
                objective="Comparar o ticket médio local à média governada da rede.",
                summary="O ticket médio está abaixo da média da rede no mesmo contexto.",
                severity="medium",
                primary_kpi="sales.average_ticket",
                condition=Compare(
                    Kpi("sales.average_ticket"),
                    "lt",
                    NetworkAverage("sales.average_ticket"),
                ),
                action_code="sales.ticket_mix_review",
                action_rationale="Revisar mix e itens por venda no escopo com desvio relativo.",
                evidence_code="sales.average_ticket_network_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail="Ticket médio local comparado à média autorizada da rede.",
                hypothesis_code="sales.local_ticket_mix_gap",
                hypothesis=(
                    "Mix local, preço médio ou quantidade de itens por venda pode explicar "
                    "o desvio frente à rede."
                ),
                expected_impact="Direcionar revisão de mix sem automatizar preço ou promoção.",
                dimensions=("branch", "channel"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:sales.average_ticket",
            ),
            _rule(
                code="sales.average_ticket_decline",
                title="Queda do ticket médio",
                objective="Detectar redução do ticket médio frente ao período anterior.",
                summary="O ticket médio caiu no escopo avaliado.",
                severity="medium",
                primary_kpi="sales.average_ticket",
                condition=Compare(
                    AbsChange("sales.average_ticket", baseline="previous"),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="sales.ticket_mix_review",
                action_rationale=(
                    "Decompor ticket, itens e preço médio antes de propor intervenção."
                ),
                evidence_code="sales.average_ticket_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail="Ticket médio atual comparado ao período anterior equivalente.",
                hypothesis_code="sales.ticket_composition_shift",
                hypothesis=(
                    "Redução de itens por venda ou mudança de mix pode explicar parte da queda."
                ),
                expected_impact="Recuperar ticket com ação comercial autorizada e mensurável.",
                dimensions=("branch", "channel", "category"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:sales.average_ticket",
            ),
            _rule(
                code="sales.cancellation_rate_above_network",
                title="Cancelamentos acima da rede",
                objective="Comparar a taxa local de cancelamento à média governada da rede.",
                summary="A taxa de cancelamento supera a média da rede.",
                severity="high",
                primary_kpi="sales.cancellation_rate",
                condition=Compare(
                    Kpi("sales.cancellation_rate"),
                    "gt",
                    NetworkAverage("sales.cancellation_rate"),
                ),
                action_code="sales.cancellation_process_review",
                action_rationale="Priorizar revisão do processo local com desvio frente à rede.",
                evidence_code="sales.cancellation_rate_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail="Taxa local de cancelamento comparada à média autorizada da rede.",
                hypothesis_code="sales.local_cancellation_process_gap",
                hypothesis=(
                    "Fluxo operacional, treinamento ou padrão de autorização pode explicar "
                    "o desvio local."
                ),
                expected_impact="Reduzir cancelamentos evitáveis com investigação controlada.",
                dimensions=("branch", "channel", "hour"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:sales.cancellation_rate",
            ),
            _rule(
                code="sales.cancellation_rate_increase",
                title="Aumento da taxa de cancelamento",
                objective=(
                    "Detectar crescimento da taxa de cancelamento frente ao período anterior."
                ),
                summary="A taxa de cancelamento aumentou no escopo avaliado.",
                severity="high",
                primary_kpi="sales.cancellation_rate",
                condition=Compare(
                    AbsChange("sales.cancellation_rate", baseline="previous"),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="sales.cancellation_process_review",
                action_rationale="Revisar motivos e operadores antes que a deterioração persista.",
                evidence_code="sales.cancellation_rate_growth",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail=(
                    "Taxa de cancelamento atual comparada ao período anterior equivalente."
                ),
                hypothesis_code="sales.cancellation_process_deterioration",
                hypothesis=(
                    "Mudança de processo, autorização ou treinamento pode explicar o crescimento."
                ),
                expected_impact=(
                    "Conter a deterioração do processo sem ação automática sobre operadores."
                ),
                dimensions=("branch", "channel", "hour"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:sales.cancellation_rate",
            ),
            _rule(
                code="sales.completed_count_decline",
                title="Queda de vendas concluídas",
                objective=(
                    "Detectar redução da quantidade de vendas concluídas frente ao período "
                    "anterior."
                ),
                summary="A quantidade de vendas concluídas caiu no escopo avaliado.",
                severity="high",
                primary_kpi="sales.completed_count",
                condition=Compare(
                    AbsChange("sales.completed_count", baseline="previous"),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="sales.revenue_drop_review",
                action_rationale="Decompor volume por canal, categoria e horário antes de agir.",
                evidence_code="sales.completed_count_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail="Vendas concluídas comparadas ao período anterior equivalente.",
                hypothesis_code="sales.transaction_volume_contraction",
                hypothesis=(
                    "Menor demanda, ruptura ou capacidade de atendimento pode explicar a queda "
                    "de transações."
                ),
                expected_impact="Identificar o componente de volume associado à queda de receita.",
                dimensions=("branch", "channel", "hour"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:sales.completed_count",
            ),
            _rule(
                code="sales.discount_rate_above_network",
                title="Taxa de desconto acima da rede",
                objective="Comparar a taxa local de desconto à média governada da rede.",
                summary="A taxa de desconto supera a média da rede.",
                severity="medium",
                primary_kpi="sales.discount_rate",
                condition=Compare(
                    Kpi("sales.discount_rate"),
                    "gt",
                    NetworkAverage("sales.discount_rate"),
                ),
                action_code="sales.ticket_mix_review",
                action_rationale=(
                    "Revisar composição das vendas com desconto sem automatizar preço."
                ),
                evidence_code="sales.discount_rate_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail="Taxa local de desconto comparada à média autorizada da rede.",
                hypothesis_code="sales.local_discount_pattern",
                hypothesis=(
                    "Mix, campanhas ou prática comercial local pode explicar o desvio frente à "
                    "rede."
                ),
                expected_impact="Reduzir desvios não explicados preservando autorização humana.",
                dimensions=("branch", "category", "product", "promotion"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:sales.discount_rate",
            ),
            _rule(
                code="sales.discount_rate_increase",
                title="Aumento da taxa de desconto",
                objective="Detectar crescimento da taxa de desconto frente ao período anterior.",
                summary="A taxa de desconto aumentou no escopo avaliado.",
                severity="medium",
                primary_kpi="sales.discount_rate",
                condition=Compare(
                    AbsChange("sales.discount_rate", baseline="previous"),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="sales.ticket_mix_review",
                action_rationale="Revisar mix e campanhas antes de qualquer alteração comercial.",
                evidence_code="sales.discount_rate_growth",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail="Taxa de desconto atual comparada ao período anterior equivalente.",
                hypothesis_code="sales.discount_intensity_growth",
                hypothesis=(
                    "Campanhas, mudança de mix ou concessão operacional pode explicar o aumento."
                ),
                expected_impact="Conter escalada de desconto sem execução financeira automática.",
                dimensions=("branch", "category", "product", "promotion"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:sales.discount_rate",
            ),
            _rule(
                code="sales.hourly_average_below_network",
                title="Venda por hora abaixo da rede",
                objective="Comparar a venda média por hora local à média governada da rede.",
                summary="A venda média por hora está abaixo da média da rede.",
                severity="medium",
                primary_kpi="sales.hourly_average",
                condition=Compare(
                    Kpi("sales.hourly_average"),
                    "lt",
                    NetworkAverage("sales.hourly_average"),
                ),
                action_code="sales.hourly_staffing_review",
                action_rationale="Revisar escala e demanda horária no escopo com desvio relativo.",
                evidence_code="sales.hourly_average_network_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail="Venda média por hora local comparada à média autorizada da rede.",
                hypothesis_code="sales.hourly_capacity_gap",
                hypothesis=(
                    "Escala, fluxo local ou distribuição da demanda pode explicar o desvio horário."
                ),
                expected_impact="Ajustar capacidade ao fluxo sem aumento automático de custo.",
                dimensions=("branch", "hour"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:sales.hourly_average",
            ),
            _rule(
                code="sales.items_per_sale_decline",
                title="Queda de itens por venda",
                objective="Detectar redução dos itens por venda frente ao período anterior.",
                summary="A quantidade média de itens por venda caiu no escopo avaliado.",
                severity="medium",
                primary_kpi="sales.items_per_sale",
                condition=Compare(
                    AbsChange("sales.items_per_sale", baseline="previous"),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="sales.ticket_mix_review",
                action_rationale="Revisar composição do carrinho e disponibilidade do mix.",
                evidence_code="sales.items_per_sale_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail="Itens por venda comparados ao período anterior equivalente.",
                hypothesis_code="sales.basket_composition_contraction",
                hypothesis=(
                    "Ruptura, mudança de missão de compra ou menor venda complementar "
                    "pode explicar a redução."
                ),
                expected_impact="Recuperar composição do carrinho com ação comercial revisada.",
                dimensions=("branch", "channel", "category"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:sales.items_per_sale",
            ),
            _rule(
                code="sales.net_revenue_below_network",
                title="Receita líquida abaixo da rede",
                objective="Comparar a receita líquida local à média governada da rede.",
                summary="A receita líquida está abaixo da média da rede no contexto comparável.",
                severity="high",
                primary_kpi="sales.net_revenue",
                condition=Compare(
                    Kpi("sales.net_revenue"),
                    "lt",
                    NetworkAverage("sales.net_revenue"),
                ),
                action_code="sales.revenue_drop_review",
                action_rationale="Decompor o desvio de receita por canal, categoria e horário.",
                evidence_code="sales.net_revenue_network_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail="Receita líquida local comparada à média autorizada da rede.",
                hypothesis_code="sales.local_revenue_gap",
                hypothesis=(
                    "Volume, mix, disponibilidade ou fluxo local pode explicar o desvio frente à "
                    "rede."
                ),
                expected_impact="Direcionar investigação ao escopo com menor desempenho relativo.",
                dimensions=("branch", "channel", "category"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:sales.net_revenue",
            ),
            _rule(
                code="sales.net_revenue_decline",
                title="Queda de receita líquida",
                objective="Detectar redução da receita líquida frente ao período anterior.",
                summary="A receita líquida caiu no escopo avaliado.",
                severity="high",
                primary_kpi="sales.net_revenue",
                condition=Compare(
                    AbsChange("sales.net_revenue", baseline="previous"),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="sales.revenue_drop_review",
                action_rationale="Decompor a queda antes de definir qualquer ação corretiva.",
                evidence_code="sales.net_revenue_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail="Receita líquida atual comparada ao período anterior equivalente.",
                hypothesis_code="sales.revenue_demand_or_supply_gap",
                hypothesis=(
                    "Mudança de demanda, ruptura, mix ou capacidade de atendimento pode explicar "
                    "parte da queda."
                ),
                expected_impact="Identificar fatores associados e definir ação humana mensurável.",
                dimensions=("branch", "channel", "category"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:sales.net_revenue",
            ),
            _rule(
                code="sales.net_revenue_downward_trend",
                title="Tendência descendente de receita líquida",
                objective=(
                    "Detectar tendência calculada negativa na menor janela suportada pela DSL."
                ),
                summary="A tendência de receita líquida está negativa na janela avaliada.",
                severity="high",
                primary_kpi="sales.net_revenue",
                condition=Compare(
                    Trend("sales.net_revenue", periods=2),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="sales.revenue_drop_review",
                action_rationale="Investigar a tendência antes que a deterioração se consolide.",
                evidence_code="sales.net_revenue_downward_trend_signal",
                evidence_type="trend",
                evidence_direction="decreasing",
                evidence_detail=(
                    "Tendência analítica da receita líquida calculada em dois períodos, "
                    "a menor janela válida da DSL."
                ),
                hypothesis_code="sales.revenue_trend_deterioration",
                hypothesis=(
                    "Deterioração gradual de volume, mix ou disponibilidade pode explicar "
                    "a tendência negativa."
                ),
                expected_impact="Antecipar deterioração recorrente com investigação rastreável.",
                dimensions=("branch", "channel", "category"),
                evaluation_window="two-period governed trend observation",
                observation_key="trend:sales.net_revenue:2",
                limitations=(
                    *_COMMON_LIMITATIONS,
                    "The two-period horizon is the minimum trend window allowed by the safe DSL.",
                ),
            ),
            _rule(
                code="sales.net_revenue_persistent_decline",
                title="Queda persistente de receita líquida",
                objective=(
                    "Detectar queda no período atual e em dois frames analíticos anteriores."
                ),
                summary="A receita líquida apresentou queda atual e persistência histórica.",
                severity="high",
                primary_kpi="sales.net_revenue",
                condition=AllOf(
                    nodes=(
                        Compare(
                            AbsChange("sales.net_revenue", baseline="previous"),
                            "lt",
                            Fixed(Decimal("0")),
                        ),
                        Persisted(
                            Compare(
                                AbsChange("sales.net_revenue", baseline="previous"),
                                "lt",
                                Fixed(Decimal("0")),
                            ),
                            periods=2,
                        ),
                    )
                ),
                action_code="sales.revenue_drop_review",
                action_rationale=(
                    "Escalar investigação da queda persistente sem automatizar decisões."
                ),
                evidence_code="sales.net_revenue_persistent_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail=(
                    "Queda atual frente ao período anterior; a persistência em dois frames "
                    "é comprovada pelo trace."
                ),
                hypothesis_code="sales.unresolved_revenue_constraint",
                hypothesis=(
                    "Restrição ainda não resolvida de demanda, mix ou disponibilidade "
                    "pode explicar a persistência."
                ),
                expected_impact=(
                    "Priorizar deterioração persistente e distinguir recuperação atual."
                ),
                dimensions=("branch", "channel", "category"),
                evaluation_window="current analytical period plus two previous analytical frames",
                reference_key="previous:sales.net_revenue",
            ),
            _rule(
                code="sales.return_rate_above_network",
                title="Devoluções acima da rede",
                objective="Comparar a taxa local de devolução à média governada da rede.",
                summary="A taxa de devolução supera a média da rede.",
                severity="high",
                primary_kpi="sales.return_rate",
                condition=Compare(
                    Kpi("sales.return_rate"),
                    "gt",
                    NetworkAverage("sales.return_rate"),
                ),
                action_code="sales.return_rate_investigation",
                action_rationale="Investigar produtos e motivos no escopo com desvio relativo.",
                evidence_code="sales.return_rate_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail="Taxa local de devolução comparada à média autorizada da rede.",
                hypothesis_code="sales.local_return_process_gap",
                hypothesis=(
                    "Produto, lote, orientação de venda ou processo local pode explicar o desvio."
                ),
                expected_impact="Reduzir devoluções por meio de investigação por produto e motivo.",
                dimensions=("branch", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:sales.return_rate",
            ),
            _rule(
                code="sales.return_rate_increase",
                title="Aumento da taxa de devolução",
                objective="Detectar crescimento da taxa de devolução frente ao período anterior.",
                summary="A taxa de devolução aumentou no escopo avaliado.",
                severity="high",
                primary_kpi="sales.return_rate",
                condition=Compare(
                    AbsChange("sales.return_rate", baseline="previous"),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="sales.return_rate_investigation",
                action_rationale="Investigar a deterioração por produto, motivo e lote.",
                evidence_code="sales.return_rate_growth",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail=(
                    "Taxa de devolução atual comparada ao período anterior equivalente."
                ),
                hypothesis_code="sales.return_issue_growth",
                hypothesis=(
                    "Mudança de produto, lote, orientação ou processo pode explicar o crescimento."
                ),
                expected_impact="Conter o aumento de devoluções com causa provável documentada.",
                dimensions=("branch", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:sales.return_rate",
            ),
            _rule(
                code="sales.revenue_per_product_below_category",
                title="Receita por produto abaixo da categoria",
                objective="Comparar a receita por produto à média governada da categoria.",
                summary="A receita por produto vendido está abaixo da média da categoria.",
                severity="medium",
                primary_kpi="sales.revenue_per_product",
                condition=Compare(
                    Kpi("sales.revenue_per_product"),
                    "lt",
                    CategoryAverage("sales.revenue_per_product"),
                ),
                action_code="sales.ticket_mix_review",
                action_rationale="Revisar produtividade do sortimento dentro da categoria.",
                evidence_code="sales.revenue_per_product_category_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail="Receita por produto comparada à média autorizada da categoria.",
                hypothesis_code="sales.category_productivity_gap",
                hypothesis=(
                    "Mix, exposição, preço médio ou disponibilidade pode explicar a menor "
                    "produtividade do produto."
                ),
                expected_impact=(
                    "Direcionar revisão do sortimento sem automatizar preço ou promoção."
                ),
                dimensions=("branch", "category", "product"),
                evaluation_window=_CATEGORY_WINDOW,
                reference_key="category_average:sales.revenue_per_product",
            ),
            _rule(
                code="sales.top10_concentration_increase",
                title="Aumento da concentração das maiores vendas",
                objective="Detectar crescimento da concentração das dez maiores vendas.",
                summary=(
                    "A concentração das dez maiores vendas aumentou frente ao período anterior."
                ),
                severity="medium",
                primary_kpi="sales.top10_concentration",
                condition=Compare(
                    AbsChange("sales.top10_concentration", baseline="previous"),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="sales.ticket_mix_review",
                action_rationale=(
                    "Revisar dependência de poucas vendas sem inferir causa automaticamente."
                ),
                evidence_code="sales.top10_concentration_growth",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail="Concentração atual comparada ao período anterior equivalente.",
                hypothesis_code="sales.revenue_concentration_growth",
                hypothesis=(
                    "Perda de diversidade do mix ou eventos pontuais pode explicar o aumento "
                    "da concentração."
                ),
                expected_impact="Reduzir vulnerabilidade a poucas transações ou itens dominantes.",
                dimensions=("branch", "channel"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:sales.top10_concentration",
            ),
            _rule(
                code="sales.units_sold_decline",
                title="Queda de unidades vendidas",
                objective="Detectar redução das unidades vendidas frente ao período anterior.",
                summary="A quantidade de unidades vendidas caiu no escopo avaliado.",
                severity="high",
                primary_kpi="sales.units_sold",
                condition=Compare(
                    AbsChange("sales.units_sold", baseline="previous"),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="sales.revenue_drop_review",
                action_rationale="Decompor queda de volume por produto, categoria e canal.",
                evidence_code="sales.units_sold_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail="Unidades vendidas comparadas ao período anterior equivalente.",
                hypothesis_code="sales.unit_demand_or_availability_gap",
                hypothesis=(
                    "Menor demanda, ruptura ou mudança de mix pode explicar a queda de unidades."
                ),
                expected_impact="Identificar a parcela de volume na deterioração de vendas.",
                dimensions=("branch", "category", "product", "channel"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:sales.units_sold",
            ),
        ),
        key=lambda rule: rule.code,
    )
)
