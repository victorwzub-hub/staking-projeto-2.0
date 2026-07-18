# ADR 0015 — Modelo canônico e landing imutável

- Status: aceito
- Data: 2026-07-17

## Contexto

ERPs de farmácias variam em identificadores, granularidade, esquema, paginação e semântica. Acoplar tabelas analíticas ao formato de cada fornecedor impediria evolução independente e tornaria replay e auditoria frágeis. Payloads volumosos também não devem competir com o PostgreSQL transacional.

## Decisão

Todo conector implementa a SDK tipada e produz `ConnectorEnvelope`. O payload entra primeiro em bucket S3 compatível, por chave imutável e hash SHA-256. PostgreSQL guarda apenas metadados, manifest, staging, estado, qualidade e linhagem. Somente registros validados passam por mapeamento explícito e `upsert` idempotente no modelo canônico relacional.

O modelo possui seis domínios: catálogo, fornecedores, vendas, compras, estoque e preços/promoções. Vendas são particionadas por data; séries temporais usam índices BRIN. Dados de tenant usam RLS forçada e FKs compostas de mesmo tenant. Credenciais são apenas referências a secret managers.

## Consequências

- Adicionar ERP exige um adapter, não alterações no domínio central.
- Replay reutiliza o mesmo manifest e não duplica fatos por identidade externa/versão.
- O landing permite prova forense e reprocessamento, com custo de object storage e política de retenção.
- Alterações incompatíveis de conector exigem nova versão e mapeamento compatível.
- PostgreSQL continua sendo a fonte de verdade operacional, mas não armazena arquivos grandes.
