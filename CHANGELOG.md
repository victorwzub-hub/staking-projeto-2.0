# Changelog

Todas as alterações relevantes serão registradas neste arquivo.

## [0.1.1] - 2026-07-14

### Added

- Componente real e acessível de status da API no frontend, com loading, sucesso, indisponibilidade e retry.
- Endpoint raiz `GET /` com metadados do serviço e links operacionais.
- Fechamento explícito do engine SQLAlchemy e do cliente Redis no shutdown.
- Validação contra configurações locais inseguras quando `APP_ENV=production`.
- Validação restrita e limitada de `X-Correlation-ID`.
- Testes de frontend para loading, sucesso, erro e retry.
- Testes backend para endpoint raiz, shutdown, configurações de produção, correlation ID e serialização de erros de validação.
- Smoke test completo da stack em `scripts/smoke-test-compose.sh`.
- Job `compose-smoke` no GitHub Actions.
- ADR de padronização em Python 3.12 e Node.js 22.

### Changed

- Dockerfiles Python passaram para Python 3.12 e builds multi-stage.
- Dockerfile web passou a usar `npm ci` e runtime standalone sem dependências de desenvolvimento.
- `@types/node` foi alinhado à linha 22.
- Versão do projeto atualizada para `0.1.1`.
- Tratamento de `RequestValidationError` passou a normalizar detalhes não serializáveis.

## [0.1.0] - 2026-07-14

### Added

- Monorepo profissional com `apps/web`, `apps/api`, `apps/worker`, `packages`, `infra`, `docs`, `scripts` e testes.
- Aplicação FastAPI com `/api/v1`, liveness, readiness, tratamento global de erros, correlation ID e logs estruturados.
- Integrações fundamentais com PostgreSQL via SQLAlchemy 2 e Redis assíncrono.
- Configuração inicial do Alembic.
- Worker Dramatiq com Redis e tarefa operacional mínima.
- Aplicação Next.js com TypeScript strict, página inicial, erro, loading, cliente HTTP e variáveis públicas validadas.
- Testes Pytest, Vitest, Testing Library e configuração Playwright.
- Docker Compose, Dockerfiles, padrões de qualidade e GitHub Actions.
- Documentação inicial, catálogo de variáveis, ADRs e roadmap.
