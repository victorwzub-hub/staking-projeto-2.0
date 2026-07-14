# Instalação e execução

## Runtimes

```text
Python 3.12
Node.js 22
npm 10
```

Os arquivos `.python-version` e `.nvmrc` registram essas versões.

## Ambiente nativo

```bash
cp .env.example .env
make bootstrap
make lint
make typecheck
make test
make build
```

Para executar API e web em terminais separados:

```bash
.venv/bin/uvicorn pharma_api.main:app --app-dir apps/api/src --reload
npm run dev
```

Valide:

```bash
curl -i http://localhost:8000/
curl -i http://localhost:8000/api/v1/health
curl -i http://localhost:8000/api/v1/readiness
curl -i http://localhost:3000
```

## Ambiente Docker

```bash
cp .env.example .env
docker compose config
docker compose up --build -d
docker compose ps
```

O gate automatizado recomendado é:

```bash
./scripts/smoke-test-compose.sh
```

Ele constrói a stack, aguarda PostgreSQL, Redis, API e web, exige readiness HTTP 200, valida o artefato standalone, testa a comunicação do container web com a API e encerra todos os serviços com `trap`.

## Troubleshooting inicial

- Readiness `503`: confirme PostgreSQL, Redis e os DSNs.
- Build web sem URL: defina `NEXT_PUBLIC_API_BASE_URL` com URL absoluta.
- Startup de produção rejeitado: revise debug, credenciais, hosts e CORS.
- Erro do Alembic: execute a partir de `apps/api` ou use `make migrate`.
- Playwright sem navegador: instale Chromium com `npx playwright install --with-deps chromium`.
- Falha no smoke: o script imprime `docker compose ps` e `docker compose logs` antes de limpar a stack.
