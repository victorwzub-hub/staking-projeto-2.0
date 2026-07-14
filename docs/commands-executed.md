# Comandos executados — Fase 1

Data: 2026-07-14

## Inspeção

```bash
find /mnt/data -maxdepth 2 -type f
find / -xdev -type d -name .git
python3 --version
node --version
npm --version
docker --version
docker compose version
git --version
```

Resultado: somente o Prompt Mestre foi encontrado; nenhum repositório ou `.git` preexistente. Python 3.13.5, Node 22.16.0, npm 10.9.2 e Git 2.47.3 disponíveis. Docker e Docker Compose ausentes.

## Instalação

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e './apps/api[dev]'
.venv/bin/pip install -e './apps/worker[dev]'
npm install
```

Resultado: instalações concluídas. O npm gerou lockfile e instalou 447 pacotes.

## Backend e worker

```bash
.venv/bin/ruff check apps/api apps/worker
.venv/bin/ruff format --check apps/api apps/worker
.venv/bin/mypy apps/api/src apps/worker/src
.venv/bin/pytest apps/api/tests apps/worker/tests -q
.venv/bin/pip check
cd apps/api && ../../.venv/bin/alembic heads
cd apps/api && ../../.venv/bin/alembic history
```

Resultado final: lint aprovado; 32 arquivos formatados; MyPy strict aprovado em 27 arquivos; 7 testes aprovados; nenhuma dependência Python quebrada; Alembic carregado sem revisions de negócio.

## Frontend

```bash
npm run lint
npm run format:check
npm run typecheck
npm run test
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1 npm run build
npm run test:e2e:list
npm ci --dry-run --no-audit --no-fund
```

Resultado final: ESLint, Prettier e TypeScript aprovados; 3 testes Vitest aprovados; build Next.js aprovado; 1 teste E2E descoberto; lockfile aceito pelo `npm ci --dry-run`.

## Runtime

```bash
APP_ENV=test DATABASE_URL='postgresql+psycopg://pharma:local@127.0.0.1:65432/pharma' \
REDIS_URL='redis://127.0.0.1:65433/0' \
.venv/bin/uvicorn pharma_api.main:app --host 127.0.0.1 --port 18000

curl http://127.0.0.1:18000/api/v1/health
curl http://127.0.0.1:18000/api/v1/readiness

PORT=13000 HOSTNAME=127.0.0.1 node apps/web/.next/standalone/apps/web/server.js
curl http://127.0.0.1:13000/
```

Resultado: API liveness HTTP 200; readiness HTTP 503 esperado sem PostgreSQL/Redis; frontend standalone HTTP 200.

## E2E e containers

```bash
PLAYWRIGHT_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e --workspace @pharma/web
npx playwright install chromium
docker compose up --build -d
```

Resultado real: E2E local não aprovado por política administrativa do Chromium (`ERR_BLOCKED_BY_ADMINISTRATOR`); download alternativo falhou por DNS. Docker Compose não pôde ser executado porque o binário Docker não existe no ambiente. O YAML do Compose foi validado estaticamente com Python/PyYAML.
