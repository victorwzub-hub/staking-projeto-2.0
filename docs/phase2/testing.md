# Estratégia de testes

## Backend

- unitários: segurança, schemas, configuração, cookies, rate limiting, migration CLI, catálogo e recursos;
- integração: PostgreSQL e Redis reais, autenticação, cookies/CSRF, onboarding vertical e RLS;
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

Vitest e Testing Library validam cliente HTTP, loading/erro, autenticação e proteção de rotas. Playwright possui cenários com interceptação controlada e cenário `real-stack.spec.ts` ativado apenas com `E2E_REAL_STACK=1`.

## Stack

`smoke-test-compose.sh` valida build, migrations, role PostgreSQL, health/readiness, frontend, worker, reinício e limpeza. No CI, a stack permanece ativa para o Playwright real e é encerrada em `always()`.
