#!/usr/bin/env python3
"""Generate the human-readable KPI catalog from the versioned semantic source."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from pharma_api.domain.analytics.kpis import KPI_CATALOG, UNAVAILABLE_KPIS  # noqa: E402


def _formula(item: object) -> str:
    formula = item.formula
    operands = ", ".join(formula.operands)
    scale = f" x {formula.scale}" if formula.scale != 1 else ""
    return f"{formula.operation}({operands}){scale}"


def render() -> str:
    lines = [
        "# Catálogo semântico de KPIs — Etapa 2C",
        "",
        "Este arquivo é gerado por `scripts/generate-kpi-catalog.py`. A fonte executável e "
        "versionada é `pharma_api.domain.analytics.kpis`; alterações de fórmula exigem nova "
        "versão e são registradas na auditoria durante a sincronização do catálogo.",
        "",
        f"KPIs operacionais: **{len(KPI_CATALOG)}**. KPIs indisponíveis: "
        f"**{len(UNAVAILABLE_KPIS)}**.",
        "",
        "## KPIs operacionais",
        "",
        "| Código | Nome | Categoria | Fórmula segura | Unidade | Direção | Versão |",
        "|---|---|---|---|---|---|---:|",
    ]
    for item in KPI_CATALOG:
        lines.append(
            f"| `{item.code}` | {item.name} | {item.category} | `{_formula(item)}` | "
            f"{item.unit} | {item.desirable_direction} | {item.version} |"
        )
    lines.extend(
        [
            "",
            "## Contrato comum",
            "",
            "Todos os indicadores operacionais declaram descrição, objetivo, granularidade, "
            "dimensões e filtros permitidos, campos necessários, fonte, periodicidade, owner, "
            "tratamento de nulos, divisão por zero, arredondamento, comparação, dependências, "
            "limitações, interpretação, impacto e drill-down. A API `GET /api/v1/analytics/kpis` "
            "expõe o contrato integral e aplica a permissão financeira.",
            "",
            "## KPIs indisponíveis",
            "",
            "| Código | Nome | Dados necessários | Motivo |",
            "|---|---|---|---|",
        ]
    )
    for item in UNAVAILABLE_KPIS:
        lines.append(
            f"| `{item.code}` | {item.name} | {', '.join(item.required_data)} | {item.reason} |"
        )
    lines.extend(
        [
            "",
            "## Regras de cálculo",
            "",
            "- A AST aceita somente `value`, `sum`, `difference`, `ratio` e `product`; não há SQL "
            "ou código fornecido por usuário.",
            "- Ausência de uma medida em um conjunto com dados equivale a zero; conjunto vazio é "
            "reportado como `no_data`.",
            "- Divisão por zero retorna `null` e `reason=zero_denominator`.",
            "- Resultados usam `ROUND_HALF_UP` com quatro casas; a UI aplica precisão da unidade.",
            "- Resultados históricos carregam `formula_version` e `data_version`.",
            "- Filtros e drill-down sempre passam por grant de tenant/empresa/filial e RLS.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    destination = ROOT / "docs" / "phase2" / "kpi-catalog.md"
    destination.write_text(render(), encoding="utf-8")


if __name__ == "__main__":
    main()
