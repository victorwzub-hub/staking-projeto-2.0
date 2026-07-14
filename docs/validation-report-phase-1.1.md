# Relatório de validação — Fase 1.1

Data: 2026-07-14
Versão: `0.1.1`

## Diagnóstico das correções

A revisão técnica estava correta nos pontos principais: a página inicial não consumia a API; não existia endpoint raiz; o lifespan não fechava recursos; Docker e CI divergiam da versão Python configurada; `X-Correlation-ID` aceitava qualquer ASCII; não havia proteção de startup de produção nem smoke test completo da stack.

Todos esses itens foram corrigidos no código. A Fase 2 não foi iniciada.

## Resultado consolidado

| Verificação | Resultado real |
|---|---|
| Instalação Node reproduzível | **Aprovada:** `npm ci --no-audit --no-fund`, 455 pacotes instalados. |
| Ruff lint | **Aprovado.** |
| Ruff format check | **Aprovado:** 35 arquivos formatados. |
| MyPy strict | **Aprovado:** 28 arquivos de código, zero problemas. |
| Pytest | **Aprovado:** 25 testes. |
| `pip check` | **Aprovado:** nenhuma dependência quebrada. |
| Alembic | **Aprovado:** `alembic heads` executou com exit code 0; não existem revisions de tabelas na fundação. |
| ESLint | **Aprovado:** zero warnings. |
| Prettier | **Aprovado.** |
| TypeScript strict | **Aprovado.** |
| Vitest/Testing Library | **Aprovado:** 6 testes em 3 arquivos. |
| Next.js standalone build | **Aprovado:** build exit code 0 e `apps/web/.next/standalone/apps/web/server.js` presente. |
| Endpoint raiz em runtime | **Aprovado:** HTTP 200 com serviço, versão, status, documentação e health URL. |
| Health em runtime | **Aprovado:** HTTP 200 e `X-Correlation-ID`. |
| Readiness nativo sem dependências | **Comportamento esperado:** HTTP 503, PostgreSQL e Redis reportados indisponíveis. Não substitui o smoke test completo. |
| Shutdown em runtime | **Aprovado:** log `application_stopped`, sem erro ao fechar Redis e SQLAlchemy. |
| Frontend standalone em runtime | **Aprovado:** HTTP 200 e estado inicial de loading presente no HTML. |
| Playwright discovery | **Aprovado:** 1 teste descoberto. |
| Playwright local | **Não aprovado:** Chromium do sistema retornou `ERR_BLOCKED_BY_ADMINISTRATOR` ao acessar `127.0.0.1:3000`. |
| Script smoke Compose | **Implementado e sintaticamente válido:** `bash -n` passou. |
| Compose e CI | **Validação estática aprovada:** YAML carregado, cinco serviços encontrados e job `compose-smoke` presente. |
| Smoke test Docker local | **Não executável neste ambiente:** exit code 127, binário `docker` ausente. |
| Git diff check | **Aprovado:** nenhuma quebra de whitespace. |

## Cobertura das exigências

### Frontend conectado à API

O componente `ApiStatus` usa `apiRequest<HealthResponse>("health")`, apresenta loading, sucesso somente após resposta real, nome/versão, indisponibilidade e retry. Há três testes específicos: loading, sucesso e erro com recuperação.

### Endpoint raiz

`GET /` retorna:

```json
{
  "service": "Pharma Intelligence SaaS",
  "version": "0.1.1",
  "status": "ok",
  "documentation_url": "/docs",
  "health_url": "/api/v1/health"
}
```

Em produção, `documentation_url` é `null` porque a documentação é desabilitada.

### Encerramento de recursos

O lifespan chama `close_redis_client()` e `close_engine()` em bloco `finally`. Os fechamentos são idempotentes e cobertos por testes dedicados.

### Segurança de configuração

Os testes confirmam rejeição em produção de debug, senha padrão, loopback em banco/Redis, wildcard CORS, CORS HTTP e CORS em loopback.

### Correlation ID

Somente `[A-Za-z0-9._-]` é aceito, com máximo de 128 caracteres. Valores longos, espaços, barras e controle são substituídos por UUID.

### Tratamento de validação

Uma rota controlada gera `RequestValidationError` com `ValueError` dentro de `ctx`. A resposta 422 foi serializada em JSON sem falha.

## Limitações reais

1. O ambiente atual possui Python 3.13.5, não Python 3.12. Docker, CI, `.python-version`, Ruff e MyPy estão alinhados a 3.12; o job backend do GitHub Actions é o gate autoritativo para essa versão.
2. Docker e Docker Compose não estão instalados. As imagens não foram construídas nem os containers iniciados localmente.
3. O E2E Playwright não passou localmente porque o Chromium fornecido pelo ambiente bloqueia loopback por política administrativa. O teste e o job de CI estão configurados, mas não são declarados como aprovados.
4. O gate final da fundação permanece condicionado ao sucesso dos jobs `frontend` e `compose-smoke` no GitHub Actions.
5. Permanece um warning de depreciação no `TestClient` entre Starlette/FastAPI e `httpx`; os 25 testes passaram e não existe falha funcional associada nesta versão.

## Conclusão do gate

A implementação da Fase 1.1 está completa no repositório. O gate local de código, testes unitários, tipagem e build está verde. O gate ambiental de Docker/E2E não pode ser marcado como verde até o workflow rodar em infraestrutura compatível.
