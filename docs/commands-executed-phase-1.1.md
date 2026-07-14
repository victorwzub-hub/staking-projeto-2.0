# Comandos executados — Fase 1.1

## Inspeção

```bash
git status --short
git log --oneline -3
git ls-files | sort
find . -type f
cat <arquivos relevantes>
python3 --version
node --version
npm --version
command -v docker
```

## Dependências e versões

```bash
npm pkg set version=0.1.1 engines.node='>=22 <23' engines.npm='>=10 <11'
npm pkg set version=0.1.1 --workspace @pharma/web
npm pkg set version=0.1.1 --workspace @pharma/contracts
npm pkg set dependencies.@pharma/contracts=0.1.1 --workspace @pharma/web
npm install --save-dev @types/node@22 --workspace @pharma/web --ignore-scripts --no-audit --no-fund
npm ci --no-audit --no-fund
```

Resultado: `npm ci` aprovado, 455 pacotes instalados. A primeira tentativa de atualização de `@types/node` falhou porque o workspace web ainda referenciava `@pharma/contracts@0.1.0`; a versão foi alinhada e o comando foi repetido com sucesso.

## Backend

```bash
.venv/bin/ruff format apps/api apps/worker
.venv/bin/ruff check apps/api apps/worker
.venv/bin/ruff format --check apps/api apps/worker
.venv/bin/mypy apps/api/src apps/worker/src
.venv/bin/pytest apps/api/tests apps/worker/tests
.venv/bin/pip check
cd apps/api && ../../.venv/bin/alembic heads
```

Resultados finais:

```text
Ruff: aprovado
Ruff format: 35 arquivos formatados
MyPy: 28 arquivos, zero problemas
Pytest: 25 passed, 1 warning
pip check: No broken requirements found
Alembic heads: exit code 0
```

## Frontend

```bash
npm run lint
npm run format --workspace @pharma/web
npm run format:check
npm run typecheck
npm run test
NEXT_TELEMETRY_DISABLED=1 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1 \
timeout 150s npm run build
npm run test:e2e:list
PLAYWRIGHT_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e
```

Resultados finais:

```text
ESLint: aprovado
Prettier: aprovado
TypeScript: aprovado
Vitest: 6 passed
Build standalone: exit code 0
Playwright discovery: 1 teste
Playwright execução: não aprovada, ERR_BLOCKED_BY_ADMINISTRATOR
```

## Runtime nativo

```bash
.venv/bin/uvicorn pharma_api.main:app \
  --app-dir apps/api/src --host 127.0.0.1 --port 8000
HOSTNAME=127.0.0.1 PORT=3000 \
  node apps/web/.next/standalone/apps/web/server.js
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/readiness
curl http://127.0.0.1:3000
```

Resultados:

```text
GET /: 200
GET /api/v1/health: 200
GET /api/v1/readiness: 503 esperado sem PostgreSQL/Redis
GET frontend: 200
Shutdown: application_stopped sem erro
```

## Infraestrutura

```bash
bash -n scripts/smoke-test-compose.sh
./scripts/smoke-test-compose.sh
python3 -c 'import yaml; yaml.safe_load(open("docker-compose.yml"))'
git diff --check
```

Resultados:

```text
Sintaxe do smoke script: aprovada
Execução smoke local: exit 127, Docker ausente
Compose YAML: cinco serviços carregados
Job compose-smoke: presente no CI
Git diff check: aprovado
```
