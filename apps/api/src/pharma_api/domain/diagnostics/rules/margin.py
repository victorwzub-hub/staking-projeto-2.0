"""Governed deterministic production rules for the margin domain."""

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

_OWNER = "margin-management"
_COMMON_LIMITATIONS = (
    "The rule reports an observed analytical signal and does not prove root cause.",
    "Price, discount, assortment or capital-allocation decisions require authorized human review.",
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
        logic_version="margin-v1",
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
        domain="margin",
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
        change_note="Initial governed margin production rule.",
    )


_PREVIOUS_WINDOW = "current analytical period versus the previous comparable period"
_NETWORK_WINDOW = "current analytical period versus the authorized network average"
_CATEGORY_WINDOW = "current analytical period versus the authorized category average"

MARGIN_RULES: tuple[GovernedRuleDefinition, ...] = tuple(
    sorted(
        (
            _rule(
                code="margin.discount_on_price_above_network",
                title="Desconto sobre preço acima da rede",
                objective="Comparar o desconto sobre preço local à média governada da rede.",
                summary="O desconto sobre preço supera a média da rede no mesmo contexto.",
                severity="medium",
                primary_kpi="margin.discount_on_price",
                condition=Compare(
                    Kpi("margin.discount_on_price"),
                    "gt",
                    NetworkAverage("margin.discount_on_price"),
                ),
                action_code="margin.discount_policy_review",
                action_rationale=(
                    "Revisar política, alçadas e campanhas antes de qualquer mudança comercial."
                ),
                evidence_code="margin.discount_on_price_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail=(
                    "Desconto sobre preço local comparado à média autorizada da rede."
                ),
                hypothesis_code="margin.local_discount_pattern",
                hypothesis=(
                    "Campanhas, composição do mix ou concessões locais podem explicar o desvio."
                ),
                expected_impact=(
                    "Reduzir erosão de margem não explicada sem alterar descontos automaticamente."
                ),
                dimensions=("branch", "category", "product", "promotion"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:margin.discount_on_price",
            ),
            _rule(
                code="margin.discount_on_price_increase",
                title="Aumento do desconto sobre preço",
                objective=(
                    "Detectar aumento direcional do desconto sobre preço frente ao período "
                    "anterior."
                ),
                summary="O desconto sobre preço aumentou no escopo avaliado.",
                severity="medium",
                primary_kpi="margin.discount_on_price",
                condition=Compare(
                    AbsChange("margin.discount_on_price", baseline="previous"),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="margin.discount_policy_review",
                action_rationale=(
                    "Revisar a origem do aumento antes de ajustar alçadas ou campanhas."
                ),
                evidence_code="margin.discount_on_price_growth",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail=(
                    "Desconto sobre preço atual comparado ao período anterior equivalente."
                ),
                hypothesis_code="margin.discount_intensity_growth",
                hypothesis=(
                    "Maior intensidade promocional ou concessões operacionais podem explicar "
                    "o aumento observado."
                ),
                expected_impact=(
                    "Conter aumento de desconto mediante decisão humana e acompanhamento."
                ),
                dimensions=("branch", "category", "product", "promotion"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:margin.discount_on_price",
            ),
            _rule(
                code="margin.gmroi_below_category",
                title="GMROI abaixo da categoria",
                objective="Comparar o GMROI do escopo à média governada da categoria.",
                summary="O GMROI está abaixo da média da categoria.",
                severity="medium",
                primary_kpi="margin.gmroi",
                condition=Compare(
                    Kpi("margin.gmroi"),
                    "lt",
                    CategoryAverage("margin.gmroi"),
                ),
                action_code="margin.gmroi_rebalance",
                action_rationale=(
                    "Revisar capital e sortimento do escopo com retorno inferior à categoria."
                ),
                evidence_code="margin.gmroi_category_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail="GMROI observado comparado à média autorizada da categoria.",
                hypothesis_code="margin.category_capital_return_gap",
                hypothesis=(
                    "Giro, lucro bruto ou capital médio em estoque podem explicar parte do desvio."
                ),
                expected_impact=(
                    "Direcionar revisão do capital sem automatizar compras ou descontinuação."
                ),
                dimensions=("branch", "category", "product"),
                evaluation_window=_CATEGORY_WINDOW,
                reference_key="category_average:margin.gmroi",
            ),
            _rule(
                code="margin.gmroi_below_network",
                title="GMROI abaixo da rede",
                objective="Comparar o GMROI local à média governada da rede.",
                summary="O GMROI está abaixo da média da rede.",
                severity="medium",
                primary_kpi="margin.gmroi",
                condition=Compare(
                    Kpi("margin.gmroi"),
                    "lt",
                    NetworkAverage("margin.gmroi"),
                ),
                action_code="margin.gmroi_rebalance",
                action_rationale=(
                    "Priorizar análise do capital empregado no escopo com retorno inferior à rede."
                ),
                evidence_code="margin.gmroi_network_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail="GMROI local comparado à média autorizada da rede.",
                hypothesis_code="margin.local_capital_return_gap",
                hypothesis=(
                    "Mix, giro ou capital médio em estoque podem estar associados ao desvio local."
                ),
                expected_impact="Melhorar retorno sobre estoque com proposta revisada por humanos.",
                dimensions=("branch", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:margin.gmroi",
            ),
            _rule(
                code="margin.gmroi_decline",
                title="Queda do GMROI",
                objective="Detectar deterioração direcional do GMROI frente ao período anterior.",
                summary="O GMROI caiu no escopo avaliado.",
                severity="medium",
                primary_kpi="margin.gmroi",
                condition=Compare(
                    AbsChange("margin.gmroi", baseline="previous"),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="margin.gmroi_rebalance",
                action_rationale=(
                    "Decompor lucro e capital em estoque antes de propor rebalanceamento."
                ),
                evidence_code="margin.gmroi_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail="GMROI atual comparado ao período anterior equivalente.",
                hypothesis_code="margin.gmroi_deterioration",
                hypothesis=(
                    "Menor lucro, maior capital médio ou giro mais lento podem explicar a queda."
                ),
                expected_impact="Interromper deterioração do retorno com decisão rastreável.",
                dimensions=("branch", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:margin.gmroi",
            ),
            _rule(
                code="margin.gross_percent_below_category",
                title="Margem percentual abaixo da categoria",
                objective=("Comparar a margem bruta percentual à média governada da categoria."),
                summary="A margem bruta percentual está abaixo da média da categoria.",
                severity="high",
                primary_kpi="margin.gross_percent",
                condition=Compare(
                    Kpi("margin.gross_percent"),
                    "lt",
                    CategoryAverage("margin.gross_percent"),
                ),
                action_code="margin.price_review",
                action_rationale=(
                    "Revisar preço, custo e tributação no contexto da categoria antes de agir."
                ),
                evidence_code="margin.gross_percent_category_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail=(
                    "Margem bruta percentual comparada à média autorizada da categoria."
                ),
                hypothesis_code="margin.category_margin_gap",
                hypothesis=(
                    "Preço, custo, tributos ou mix podem explicar parte do desvio da categoria."
                ),
                expected_impact=(
                    "Recuperar margem relativa com revisão autorizada de preço e custo."
                ),
                dimensions=("branch", "category", "product"),
                evaluation_window=_CATEGORY_WINDOW,
                reference_key="category_average:margin.gross_percent",
            ),
            _rule(
                code="margin.gross_percent_below_network",
                title="Margem percentual abaixo da rede",
                objective="Comparar a margem bruta percentual local à média governada da rede.",
                summary="A margem bruta percentual está abaixo da média da rede.",
                severity="high",
                primary_kpi="margin.gross_percent",
                condition=Compare(
                    Kpi("margin.gross_percent"),
                    "lt",
                    NetworkAverage("margin.gross_percent"),
                ),
                action_code="margin.price_review",
                action_rationale=(
                    "Priorizar revisão de preço e custo no escopo com desvio frente à rede."
                ),
                evidence_code="margin.gross_percent_network_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail="Margem percentual local comparada à média autorizada da rede.",
                hypothesis_code="margin.local_margin_gap",
                hypothesis=("Preço, custo, tributos ou composição local podem explicar o desvio."),
                expected_impact="Direcionar revisão de margem sem ajuste automático de preços.",
                dimensions=("branch", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:margin.gross_percent",
            ),
            _rule(
                code="margin.gross_percent_decline",
                title="Queda da margem bruta percentual",
                objective=(
                    "Detectar deterioração direcional da margem percentual frente ao período "
                    "anterior."
                ),
                summary="A margem bruta percentual caiu no escopo avaliado.",
                severity="high",
                primary_kpi="margin.gross_percent",
                condition=Compare(
                    AbsChange("margin.gross_percent", baseline="previous"),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="margin.price_review",
                action_rationale=(
                    "Decompor preço, custo e desconto antes de preparar qualquer reajuste."
                ),
                evidence_code="margin.gross_percent_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail=(
                    "Margem bruta percentual atual comparada ao período anterior equivalente."
                ),
                hypothesis_code="margin.percentage_margin_erosion",
                hypothesis=(
                    "Custo, desconto, preço ou mix podem estar associados à deterioração observada."
                ),
                expected_impact="Conter erosão de margem com intervenção humana mensurável.",
                dimensions=("branch", "category", "product", "promotion"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:margin.gross_percent",
            ),
            _rule(
                code="margin.gross_profit_decline",
                title="Queda do lucro bruto",
                objective="Detectar redução direcional do lucro bruto frente ao período anterior.",
                summary="O lucro bruto caiu no escopo avaliado.",
                severity="high",
                primary_kpi="margin.gross_profit",
                condition=Compare(
                    AbsChange("margin.gross_profit", baseline="previous"),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="margin.price_review",
                action_rationale=(
                    "Decompor volume, preço, desconto e custo antes de recomendar intervenção."
                ),
                evidence_code="margin.gross_profit_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail="Lucro bruto atual comparado ao período anterior equivalente.",
                hypothesis_code="margin.gross_profit_deterioration",
                hypothesis=(
                    "Menor volume, preço, desconto ou custo podem explicar parte da queda."
                ),
                expected_impact="Identificar e tratar o componente econômico da deterioração.",
                dimensions=("branch", "category", "product", "channel"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:margin.gross_profit",
            ),
            _rule(
                code="margin.gross_profit_downward_trend",
                title="Tendência de queda do lucro bruto",
                objective="Detectar tendência governada negativa do lucro bruto em dois períodos.",
                summary="O lucro bruto apresenta tendência negativa no escopo avaliado.",
                severity="high",
                primary_kpi="margin.gross_profit",
                condition=Compare(
                    Trend("margin.gross_profit", periods=2),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="margin.price_review",
                action_rationale=(
                    "Revisar a trajetória de preço, custo e mix antes que a queda se consolide."
                ),
                evidence_code="margin.gross_profit_downward_trend_signal",
                evidence_type="trend",
                evidence_direction="decreasing",
                evidence_detail="Tendência parametrizada de dois períodos do lucro bruto.",
                hypothesis_code="margin.gross_profit_trend_pressure",
                hypothesis=(
                    "Pressão recorrente de custo, desconto ou mix pode explicar a tendência."
                ),
                expected_impact="Antecipar deterioração sustentada sem automatizar preço.",
                dimensions=("branch", "category", "product"),
                evaluation_window="two-period governed trend observation",
                observation_key="trend:margin.gross_profit:2",
            ),
            _rule(
                code="margin.gross_profit_negative",
                title="Lucro bruto negativo",
                objective="Detectar lucro bruto abaixo da fronteira econômica de zero.",
                summary="O lucro bruto observado é negativo no escopo avaliado.",
                severity="critical",
                primary_kpi="margin.gross_profit",
                condition=Compare(
                    Kpi("margin.gross_profit"),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="margin.negative_margin_cleanup",
                action_rationale=(
                    "Investigar preço, custo e tributos antes de qualquer correção financeira."
                ),
                evidence_code="margin.gross_profit_negative_signal",
                evidence_type="threshold",
                evidence_direction="below",
                evidence_detail="Lucro bruto observado abaixo da fronteira econômica de zero.",
                hypothesis_code="margin.negative_profit_condition",
                hypothesis=(
                    "Preço abaixo do custo, custo incorreto ou tributação podem explicar o sinal."
                ),
                expected_impact="Eliminar exposição a resultado bruto negativo com revisão humana.",
                dimensions=("branch", "category", "product"),
                evaluation_window="current analytical period",
            ),
            _rule(
                code="margin.gross_profit_persistent_negative",
                title="Lucro bruto negativo persistente",
                objective=(
                    "Detectar lucro bruto negativo no período atual e nos dois frames anteriores."
                ),
                summary=(
                    "O lucro bruto permaneceu negativo no período atual e no histórico exigido."
                ),
                severity="critical",
                primary_kpi="margin.gross_profit",
                condition=AllOf(
                    nodes=(
                        Compare(
                            Kpi("margin.gross_profit"),
                            "lt",
                            Fixed(Decimal("0")),
                        ),
                        Persisted(
                            Compare(
                                Kpi("margin.gross_profit"),
                                "lt",
                                Fixed(Decimal("0")),
                            ),
                            periods=2,
                        ),
                    )
                ),
                action_code="margin.negative_margin_cleanup",
                action_rationale=(
                    "Escalar o saneamento do sinal persistente sem alterar preços automaticamente."
                ),
                evidence_code="margin.gross_profit_persistent_negative_signal",
                evidence_type="threshold",
                evidence_direction="below",
                evidence_detail=(
                    "Lucro bruto atual negativo; a persistência nos dois frames anteriores "
                    "é registrada no trace."
                ),
                hypothesis_code="margin.unresolved_negative_profit_condition",
                hypothesis=(
                    "Problema ainda não resolvido de preço, custo ou cadastro pode explicar "
                    "a persistência."
                ),
                expected_impact="Priorizar perda persistente e comprovar recuperação atual.",
                dimensions=("branch", "category", "product"),
                evaluation_window="current analytical frame plus two previous frames",
            ),
            _rule(
                code="margin.markup_below_category",
                title="Markup abaixo da categoria",
                objective="Comparar o markup do escopo à média governada da categoria.",
                summary="O markup está abaixo da média da categoria.",
                severity="medium",
                primary_kpi="margin.markup",
                condition=Compare(
                    Kpi("margin.markup"),
                    "lt",
                    CategoryAverage("margin.markup"),
                ),
                action_code="margin.price_review",
                action_rationale=(
                    "Revisar custo e preço em relação à categoria antes de propor ajuste."
                ),
                evidence_code="margin.markup_category_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail="Markup observado comparado à média autorizada da categoria.",
                hypothesis_code="margin.category_markup_gap",
                hypothesis=(
                    "Custo, preço ou composição do produto podem explicar o desvio da categoria."
                ),
                expected_impact="Recuperar markup relativo mediante decisão comercial autorizada.",
                dimensions=("branch", "category", "product"),
                evaluation_window=_CATEGORY_WINDOW,
                reference_key="category_average:margin.markup",
            ),
            _rule(
                code="margin.markup_below_network",
                title="Markup abaixo da rede",
                objective="Comparar o markup local à média governada da rede.",
                summary="O markup está abaixo da média da rede.",
                severity="medium",
                primary_kpi="margin.markup",
                condition=Compare(
                    Kpi("margin.markup"),
                    "lt",
                    NetworkAverage("margin.markup"),
                ),
                action_code="margin.price_review",
                action_rationale=(
                    "Priorizar revisão do escopo com markup inferior à referência da rede."
                ),
                evidence_code="margin.markup_network_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail="Markup local comparado à média autorizada da rede.",
                hypothesis_code="margin.local_markup_gap",
                hypothesis=(
                    "Diferença de custo, preço ou mix pode estar associada ao desvio local."
                ),
                expected_impact="Reduzir desvio de markup sem execução automática de preço.",
                dimensions=("branch", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:margin.markup",
            ),
            _rule(
                code="margin.negative_margin_rate_above_network",
                title="Margem negativa acima da rede",
                objective=(
                    "Comparar a taxa local de produtos com margem negativa à média da rede."
                ),
                summary="A taxa de produtos com margem negativa supera a média da rede.",
                severity="critical",
                primary_kpi="margin.negative_margin_rate",
                condition=Compare(
                    Kpi("margin.negative_margin_rate"),
                    "gt",
                    NetworkAverage("margin.negative_margin_rate"),
                ),
                action_code="margin.negative_margin_cleanup",
                action_rationale=("Priorizar saneamento do escopo com exposição superior à rede."),
                evidence_code="margin.negative_margin_rate_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail=(
                    "Taxa local de produtos com margem negativa comparada à média da rede."
                ),
                hypothesis_code="margin.local_negative_margin_exposure",
                hypothesis=("Preço, custo, tributo ou cadastro local podem explicar o desvio."),
                expected_impact=(
                    "Reduzir exposição relativa a margem negativa com auditoria humana."
                ),
                dimensions=("branch", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:margin.negative_margin_rate",
            ),
            _rule(
                code="margin.negative_margin_rate_increase",
                title="Aumento da taxa de margem negativa",
                objective=("Detectar aumento direcional da taxa de produtos com margem negativa."),
                summary="A taxa de produtos com margem negativa aumentou no escopo avaliado.",
                severity="critical",
                primary_kpi="margin.negative_margin_rate",
                condition=Compare(
                    AbsChange("margin.negative_margin_rate", baseline="previous"),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="margin.negative_margin_cleanup",
                action_rationale=(
                    "Investigar os novos itens expostos antes que a condição se amplie."
                ),
                evidence_code="margin.negative_margin_rate_growth",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail=(
                    "Taxa de margem negativa atual comparada ao período anterior equivalente."
                ),
                hypothesis_code="margin.negative_margin_exposure_growth",
                hypothesis=(
                    "Mudança de custo, preço, desconto ou cadastro pode explicar o aumento."
                ),
                expected_impact="Conter expansão de prejuízo unitário sem automação financeira.",
                dimensions=("branch", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:margin.negative_margin_rate",
            ),
            _rule(
                code="margin.negative_margin_rate_positive",
                title="Produtos com margem negativa",
                objective=(
                    "Detectar qualquer taxa positiva de produtos vendidos com margem negativa."
                ),
                summary="Existe produto vendido com margem negativa no escopo avaliado.",
                severity="critical",
                primary_kpi="margin.negative_margin_rate",
                condition=Compare(
                    Kpi("margin.negative_margin_rate"),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="margin.negative_margin_cleanup",
                action_rationale=(
                    "Listar e auditar os itens antes de preparar correção de preço ou cadastro."
                ),
                evidence_code="margin.negative_margin_rate_positive_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail=(
                    "Taxa observada de produtos vendidos com margem negativa acima de zero."
                ),
                hypothesis_code="margin.negative_margin_product_condition",
                hypothesis=(
                    "Preço, custo, tributo ou desconto pode explicar parte dos itens expostos."
                ),
                expected_impact="Eliminar vendas abaixo do custo após revisão autorizada.",
                dimensions=("branch", "category", "product"),
                evaluation_window="current analytical period",
            ),
            _rule(
                code="margin.price_dispersion_above_network",
                title="Dispersão de preços acima da rede",
                objective="Comparar a dispersão local de preços à média governada da rede.",
                summary="A dispersão de preços supera a média da rede.",
                severity="medium",
                primary_kpi="margin.price_dispersion",
                condition=Compare(
                    Kpi("margin.price_dispersion"),
                    "gt",
                    NetworkAverage("margin.price_dispersion"),
                ),
                action_code="margin.price_dispersion_review",
                action_rationale=(
                    "Investigar divergências e exceções antes de propor alinhamento de preços."
                ),
                evidence_code="margin.price_dispersion_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail="Dispersão local comparada à média autorizada da rede.",
                hypothesis_code="margin.local_price_dispersion",
                hypothesis=(
                    "Custos regionais, campanhas ou cadastros podem explicar a dispersão observada."
                ),
                expected_impact="Reduzir dispersão injustificada preservando exceções autorizadas.",
                dimensions=("branch", "category", "product"),
                evaluation_window=_NETWORK_WINDOW,
                reference_key="network_average:margin.price_dispersion",
            ),
            _rule(
                code="margin.profit_per_sale_decline",
                title="Queda do lucro bruto por venda",
                objective=(
                    "Detectar redução direcional do lucro bruto por venda frente ao período "
                    "anterior."
                ),
                summary="O lucro bruto por venda caiu no escopo avaliado.",
                severity="high",
                primary_kpi="margin.profit_per_sale",
                condition=Compare(
                    AbsChange("margin.profit_per_sale", baseline="previous"),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="margin.price_review",
                action_rationale=(
                    "Revisar preço, desconto e mix por transação antes de propor intervenção."
                ),
                evidence_code="margin.profit_per_sale_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail=(
                    "Lucro bruto por venda atual comparado ao período anterior equivalente."
                ),
                hypothesis_code="margin.transaction_profit_compression",
                hypothesis=("Mudança de mix, desconto, preço ou custo pode explicar a compressão."),
                expected_impact="Recuperar lucro por transação com decisão comercial rastreável.",
                dimensions=("branch", "channel", "category"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:margin.profit_per_sale",
            ),
            _rule(
                code="margin.profit_per_unit_decline",
                title="Queda do lucro bruto por unidade",
                objective=(
                    "Detectar redução direcional do lucro por unidade frente ao período anterior."
                ),
                summary="O lucro bruto por unidade caiu no escopo avaliado.",
                severity="high",
                primary_kpi="margin.profit_per_unit",
                condition=Compare(
                    AbsChange("margin.profit_per_unit", baseline="previous"),
                    "lt",
                    Fixed(Decimal("0")),
                ),
                action_code="margin.price_review",
                action_rationale=(
                    "Revisar preço, custo e desconto unitário antes de qualquer correção."
                ),
                evidence_code="margin.profit_per_unit_decline_signal",
                evidence_type="comparison",
                evidence_direction="decreasing",
                evidence_detail=(
                    "Lucro bruto por unidade atual comparado ao período anterior equivalente."
                ),
                hypothesis_code="margin.unit_profit_compression",
                hypothesis=(
                    "Custo, preço, desconto ou tributo pode explicar a redução por unidade."
                ),
                expected_impact="Recuperar resultado unitário sem alteração automática de preço.",
                dimensions=("branch", "category", "product"),
                evaluation_window=_PREVIOUS_WINDOW,
                reference_key="previous:margin.profit_per_unit",
            ),
        ),
        key=lambda rule: rule.code,
    )
)
