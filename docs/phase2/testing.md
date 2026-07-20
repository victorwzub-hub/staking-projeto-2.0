# Estratégia de testes

## Backend

- unitários: segurança, schemas, configuração, cookies, rate limiting, migration CLI, catálogo, fórmulas semânticas e recursos;
- integração: PostgreSQL e Redis reais, autenticação, cookies/CSRF, onboarding vertical, pipeline canônico, refresh analítico e RLS;
- migration: upgrade, downgrade, novo upgrade e idempotência;
- cobertura com `pytest-cov`.

Integração exige:

```bash
TEST_ADMIN_DATABASE_URL=...
TEST_DATABASE_URL=...
TEST_REDIS_URL=...
pytest apps/api/tests/integration -m integration
```

## Frontend

Vitest e Testing Library validam cliente HTTP, loading/erro, autenticação, proteção de rotas e dashboard analítico. Playwright possui cenários com interceptação controlada e cenário `real-stack.spec.ts` ativado apenas com `E2E_REAL_STACK=1`.

## Stack

`smoke-test-compose.sh` valida build, migrations, role PostgreSQL, health/readiness, frontend, worker, reinício e limpeza. No CI, a stack permanece ativa para o Playwright real, que importa dados, aguarda a versão analítica, consulta KPI não vazio, valida lineage/metas/idempotência e bloqueio cross-tenant.

## Etapa 2C

- `test_analytics.py`: catálogo com 120 KPIs, AST fechada, divisão por zero/nulos/arredondamento, campos suportados, modelos, permissões, metas e exportação segura;
- `test_phase2b_pipeline.py`: carga real em PostgreSQL, refresh repetido sem duplicação, versão, agregados, lineage e RLS de outro tenant;
- `page.test.tsx`: carregamento do catálogo/resultados/comparações, filtros e estados da UI;
- `benchmark-analytics.py --profile smoke`: determinismo e separação dos estágios; capacidade de 1 milhão fica para staging;
- drift do OpenAPI e do catálogo Markdown: ambos são regenerados no CI e precisam resultar em diff vazio.
