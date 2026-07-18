# ADR 0016 — Warehouse analítico e camada semântica no PostgreSQL

## Status

Aceita em 2026-07-18.

## Contexto

A Etapa 2B já entrega dados canônicos, lineage, qualidade e processamento idempotente. A Etapa 2C precisa disponibilizar análises por tenant e escopo, manter fórmulas auditáveis, responder dashboards sem consultar diretamente o modelo operacional e evitar uma segunda infraestrutura antes de existir evidência de volume que a justifique.

## Decisão

Usar PostgreSQL 17 como primeiro warehouse, em schema lógico composto por:

- dimensões conformadas SCD2 em `analytics_dimensions`;
- fatos tipados em `analytics_facts`, com grão natural único, medidas JSONB e vínculos de origem;
- agregados diários por escopo e dimensões de uso frequente em `analytics_daily_aggregates`;
- catálogo e versões de fórmula em `analytics_kpi_definitions` e `analytics_kpi_formula_versions`;
- resultados materializados, jobs, versão de dados, lineage e metas nas demais tabelas `analytics_*`.

A camada semântica é código versionado. Fórmulas usam uma AST fechada (`value`, `sum`, `difference`, `ratio`, `product`) e nunca aceitam SQL ou código do usuário. O cache Redis inclui tenant, grants, filtros, versão da fórmula e `data_version`; uma carga bem-sucedida incrementa a versão e invalida logicamente os resultados antigos.

O worker faz refresh incremental após um lote canônico, com lookback para atrasos. Backfill e recompute são operações explícitas, auditadas e serializadas por advisory lock de tenant. RLS forçada, grants de escopo e filtros de autorização são aplicados em fatos, agregados, metas e endpoints.

## Consequências

Benefícios: implantação simples, transações consistentes com o canônico, lineage direto, migrations únicas e baixo custo operacional inicial. Custos: JSONB exige disciplina de índices/agregados; cargas analíticas competem por recursos com a API; retenção e VACUUM precisam ser acompanhados.

Migrar para um warehouse dedicado passa a ser considerado quando benchmarks reais mostrarem uma destas condições persistentes: p95 acima do SLO mesmo com índices e particionamento, volume superior à janela operacional do PostgreSQL, contenção mensurável com OLTP, ou necessidade de workloads colunares/BI que não possam ser isolados. O contrato semântico e os grãos permanecem portáveis.

## Alternativas rejeitadas

- Consultar tabelas canônicas diretamente: acopla dashboards ao OLTP e duplica fórmulas.
- Fórmulas SQL configuráveis: aumenta a superfície de injeção, autorização e regressão.
- Adotar imediatamente ClickHouse/BigQuery/Snowflake: acrescenta CDC, consistência, custo e operação sem benchmark que demonstre necessidade.
