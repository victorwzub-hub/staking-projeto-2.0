# Escopo executado — Fase 1

## Incluído

- Inspeção do ambiente e registro de que não havia repositório preexistente.
- Arquitetura inicial em monólito modular.
- Monorepo com web, API, worker, contratos, infraestrutura, documentação e scripts.
- PostgreSQL, Redis, SQLAlchemy 2, Alembic e Dramatiq preparados.
- FastAPI com configuração por ambiente, API `/api/v1`, health, readiness, erros globais, correlation ID e logs estruturados.
- Next.js com TypeScript strict, layout, home provisória, erro, loading, cliente HTTP e variáveis públicas seguras.
- Pytest, Ruff, MyPy, Vitest, Testing Library, Playwright, ESLint e Prettier.
- Dockerfiles, Docker Compose, GitHub Actions e Dependabot.
- Documentação obrigatória e ADRs.

## Deliberadamente excluído

- Autenticação e autorização.
- Multi-tenant e entidades de empresa/filial/usuário.
- Billing.
- Regras farmacêuticas, KPIs, dashboards completos e simuladores.
- Conectores ERP reais.
- Machine Learning e LLM.
- Módulos financeiros e comerciais.

A Fase 2 só deve começar após a validação desta fundação no ambiente da equipe com Docker disponível.
