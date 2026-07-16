# Instalação, execução e testes

## Runtimes

Python 3.12, Node.js 22, npm 10, PostgreSQL 17 e Redis 8.

## Dependências

```bash
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e './apps/api[dev]' -e './apps/worker[dev]'
npm ci
cp .env.example .env
```

## Banco

Use uma role administrativa para migration e uma role de aplicação sem `BYPASSRLS` para runtime.

```bash
cd apps/api
MIGRATION_DATABASE_URL='postgresql+psycopg://...' alembic upgrade head
```

Em testes de integração:

```bash
TEST_ADMIN_DATABASE_URL='postgresql+psycopg://...' \
TEST_DATABASE_URL='postgresql+psycopg://...' \
TEST_REDIS_URL='redis://127.0.0.1:6379/15' \
python scripts/prepare-integration-database.py
```

## Processos

```bash
.venv/bin/uvicorn pharma_api.main:app --app-dir apps/api/src --reload
npm run dev
.venv/bin/dramatiq pharma_worker.tasks --path apps/worker/src --path apps/api/src
```

## Testes locais sem serviços

```bash
PYTHONPATH=apps/api/src:apps/worker/src pytest apps/api/tests apps/worker/tests -m 'not integration'
ruff check apps/api apps/worker
ruff format --check apps/api apps/worker
mypy apps/api/src apps/worker/src
npm run format:check
npm run lint
npm run typecheck
npm run test:coverage
npm run build
```

## Integração real

```bash
./scripts/test-migrations.sh
pytest apps/api/tests/integration -m integration
./scripts/smoke-test-compose.sh
```

Esses comandos exigem PostgreSQL, Redis e/ou Docker reais. Não substitua por SQLite ou mocks.
