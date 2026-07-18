# Plataforma analítica — Etapa 2C

## Fluxo e limites

`canônico 2B → refresh incremental → dimensões/fatos → agregados diários → camada semântica → cache/API → dashboard`.

O canônico continua sendo a fonte de verdade operacional. O warehouse é derivado e reconstruível. Cada fato preserva `source_batch_id`, `source_table`, `source_record_id`, `source_version`, `occurred_at`, tenant, empresa e filial. `analytics_lineage` registra contagens e watermarks do processamento; `analytics_data_versions` publica a versão somente após o refresh concluir.

## Dimensões conformadas

Data, hora, tenant, grupo econômico, empresa, filial, produto, identificador de produto, categoria/hierarquia, marca, fabricante, fornecedor, canal, meio de pagamento, origem da venda, tipo de movimento, promoção, faixa de preço e classificação comercial.

Os membros mutáveis usam SCD2: chave natural estável, hash de atributos, `valid_from`, `valid_to` e `is_current`. Nova versão fecha a anterior; fatos apontam para a versão dimensional válida na carga. Hierarquias usam `parent_natural_key` sem abrir acesso fora do tenant.

## Fatos e grãos

| Tipo | Uma linha representa | Medidas principais |
|---|---|---|
| `sale` | uma venda canônica | receita, descontos, custo, venda concluída/cancelada |
| `sale_item` | um item de venda | unidades, preço, receita, custo, margem |
| `payment` | um pagamento de venda | valor e contagem por método |
| `return` | uma devolução/ajuste | valor, unidades, motivo |
| `purchase` | um pedido de compra | valor, status e lead time |
| `purchase_item` | uma linha comprada | quantidade, custo e recebimento |
| `receipt` | um recebimento | prazo, quantidade e conformidade |
| `inventory_movement` | um movimento de estoque | entrada, saída e valor |
| `stock_snapshot` | saldo de produto/filial em um instante | disponível, reservado, custo, validade |
| `price` | uma vigência de preço | preço, custo e dispersão |
| `promotion` | produto participante de promoção | período e impacto |
| `cost` | vigência de custo fornecedor/produto | custo e variação |
| `data_quality` | resultado de regra de qualidade | avaliados, falhas e score |
| `import_execution` | uma execução de importação/refresh | duração, lag, backfill e recompute |

`grain_key` é determinística e única por tenant/tipo; reexecutar a mesma janela não duplica fatos. Snapshots são semiaditivos: consultas temporais selecionam o último ponto, não somam saldos ao longo do tempo.

## Agregados, filtros e camada semântica

Agregados diários cobrem escopo, produto, categoria, fornecedor, canal, pagamento e movimento. A consulta escolhe o menor grão compatível e limita combinações de alta cardinalidade. Os filtros públicos são período, grupo, empresa, filial, produto, categoria, marca, fornecedor e canal; todos são intersectados com grants e RLS.

O catálogo executável possui 120 KPIs operacionais. Cada definição declara fórmula, unidade, direção desejável, grão, dimensões, filtros, fonte, periodicidade, owner, versão, regras de nulo/divisão/arredondamento, dependências, limitações, interpretação, impacto e drill-down. O arquivo gerado [`kpi-catalog.md`](../phase2/kpi-catalog.md) é verificado contra o código no CI.

Comparações suportadas: período anterior equivalente, mesmo período do ano anterior, média móvel de 28 dias, rede autorizada e categoria do produto. Respostas carregam `formula_version`, `data_version`, freshness, qualidade e estado do cache.

## Segurança e auditoria

RLS está habilitada e forçada nas dez tabelas analíticas. O role da aplicação não usa `BYPASSRLS`. A API exige `analytics.view`; valores financeiros exigem `analytics.financial`; detalhe, exportação, metas e operação usam permissões próprias. A listagem dimensional e as comparações de rede nunca ampliam o grant do usuário. Acesso cross-tenant retorna ausência, sem revelar a existência do recurso.

Criação/alteração de metas, enfileiramento de refresh/backfill/recompute, exportação e sincronização de versão de fórmula geram auditoria. CSV neutraliza células iniciadas por caracteres interpretados como fórmula.

## Falhas e consistência

Jobs são `queued → running → completed|failed|cancelled`, possuem tentativas limitadas e métricas persistidas. A versão de dados só muda no sucesso; falha mantém a versão anterior consultável. Lookback absorve chegada tardia; backfill cobre janela histórica; recompute refaz derivados sem editar dados de origem. O advisory lock impede dois writers para o mesmo tenant.
