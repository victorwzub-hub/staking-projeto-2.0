# Relatório de validação — Fase 1

Data: 2026-07-14

## Resultado consolidado

| Verificação | Resultado real |
|---|---|
| Instalação Python | Aprovada: API e worker instalados em modo editável. |
| Instalação Node | Aprovada: 447 pacotes instalados e `package-lock.json` criado. |
| Ruff lint | Aprovado. |
| Ruff format | Aprovado: 32 arquivos formatados. |
| MyPy strict | Aprovado: 27 arquivos, zero problemas. |
| Pytest | Aprovado: 7 testes. Há 1 warning de depreciação entre FastAPI/Starlette TestClient e httpx. |
| ESLint | Aprovado, zero warnings. |
| Prettier | Aprovado. |
| TypeScript strict | Aprovado. |
| Vitest | Aprovado: 3 testes em 2 arquivos. |
| Next.js build | Aprovado; páginas `/` e `/_not-found` geradas estaticamente. |
| Playwright discovery | Aprovado: 1 teste Chromium descoberto. |
| Playwright execução local | Não concluída por restrição externa do ambiente: Chromium do sistema bloqueou loopback por política administrativa e o download do navegador isolado falhou por DNS. Não foi declarado como aprovado. |
| API liveness em runtime | Aprovado: HTTP 200 e `X-Correlation-ID`. |
| API readiness em runtime sem dependências | Aprovado: HTTP 503 com PostgreSQL e Redis identificados como indisponíveis. |
| Frontend standalone em runtime | Aprovado: HTTP 200 e conteúdo esperado. |
| Alembic | Configuração carregada; `alembic heads` e `alembic history` executaram sem erro. Não há revisions porque não existem tabelas de negócio na Fase 1. |
| `pip check` | Aprovado: nenhuma dependência quebrada. |
| Compose | YAML carregado e cinco serviços obrigatórios verificados estaticamente. |
| Containers | Não executados: binário Docker/Compose indisponível no ambiente. |

## Erros encontrados e corrigidos

1. Imports Python fora do padrão Ruff.
2. Tipagem insuficiente em testes Pytest e logger estruturado.
3. Import do broker do worker marcado como não utilizado.
4. Vitest coletando indevidamente o arquivo E2E do Playwright.
5. Teste React sem imports explícitos dos globals do Vitest.
6. Prettier analisando artefatos gerados de `.next` e Playwright.
7. Dockerfile do worker instalando o pacote sem a dependência Dramatiq.
8. MyPy inicialmente executado sem configuração strict compartilhada na raiz.

Todos os itens acima foram corrigidos e revalidados.
