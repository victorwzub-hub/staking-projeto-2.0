# Etapa 2A.2 — relatório de integração, validação e hardening

Data da validação: 2026-07-17.

## Resultado executivo

A Etapa 2A.2 já estava integralmente presente no commit-base. O pacote recebido foi integrado
semanticamente, sem sobrescrita cega, e o código foi endurecido em três pontos encontrados na
revisão: uma consulta N+1 na listagem de papéis, a corrida de convites pendentes e a cobertura
incompleta da matriz de escopo no CI.

Os gates locais de código, migração, segurança, contrato, unidade e integração estão verdes.
O smoke completo via Docker Compose, o Playwright sobre a stack real e a varredura das imagens
não puderam ser executados localmente porque o host não oferece a virtualização exigida pelo
Docker Desktop. Esses gates continuam obrigatórios no GitHub Actions e não são considerados
validados por este relatório até a execução remota.

## Baseline e integração do pacote

- Branch-base: `phase2/integration-20260716-174330`.
- Commit-base: `79e8256cb83f587e67cd8f36ff35c8953b23be26`.
- Branch de trabalho: `codex/phase2-2a2-production-hardening`.
- Alteração preexistente preservada e excluída dos commits: remoção local de
  `pharma-intelligence-saas-phase1.1-final.zip`.
- Pacote: `pharma-sprint-2a2-scope-enforcement.zip`.
- SHA-256 do pacote:
  `18F92A66F0AB561906B795114E8A81EBF1888318BDF873187E1392447E764FDE`.

`_PACKAGE_INFO.txt` e `_MANIFEST.txt` foram lidos integralmente. Os 21 caminhos do manifesto
existem no checkout e os 21 hashes SHA-256 são idênticos aos arquivos correspondentes do
repositório. Nenhum arquivo do pacote foi copiado sobre trabalho existente.

A Etapa 2A.1 está presente no histórico, incluindo a fundação de identidade/tenancy e os
grants anteriores à autorização escopada. A migração `20260716_0001` aparece em múltiplos
commits e branches e, por isso, foi tratada como publicada: não foi reescrita.

## Correções e endurecimentos

### Convites concorrentes

- Nova migração incremental `20260717_0002`, mantendo `20260716_0001` intacta.
- Migração expira registros vencidos, revoga duplicatas históricas preservando o convite mais
  novo e cria o índice parcial único
  `uq_invitations_pending_tenant_email (tenant_id, normalized_email) WHERE status = 'pending'`.
- O serviço expira convites vencidos sob lock antes de criar outro e força `flush` para que a
  violação ocorra dentro da transação da requisição.
- A colisão da nova constraint preserva o contrato público existente:
  HTTP 409 com código `invitation_already_pending`.
- Teste de contenção real abre oito transações PostgreSQL simultâneas; uma vence e sete recebem
  `IntegrityError`.

### RBAC e desempenho

- `list_roles` deixou de executar uma consulta de permissões para cada papel.
- Papéis e permissões são carregados por um único `SELECT` com joins e agrupados em memória.
- Teste de regressão verifica uma única chamada a `AsyncSession.execute`, independentemente da
  quantidade de papéis/permissões.

### Banco, CI e portabilidade

- Alembic e pytest usam `SelectorEventLoop` somente no Windows, necessário para sockets
  assíncronos do psycopg; Linux mantém o loop padrão.
- Os scripts de migração e smoke exigem a nova head `20260717_0002`.
- A matriz `test_scoped_authorization_matrix.py` foi incluída no job negativo obrigatório do CI.
- Um teste legado de savepoint foi corrigido para que a exceção alcance o contexto transacional
  e provoque rollback antes da liberação do savepoint.

### Formulários web e E2E real-stack

- A primeira execução remota do Compose revelou severidade média: a API criava a empresa com
  HTTP 201, mas oito handlers React acessavam `event.currentTarget` depois de um `await`.
  O `currentTarget` já estava nulo, interrompendo o reset do formulário e o reload da lista.
- Cada handler agora captura o elemento `<form>` antes da operação assíncrona.
- Uma regressão de componente comprova criação, reset e reload após a resposta assíncrona.
- O cenário real-stack aceita `/app` nos retries após uma tentativa anterior ter concluído o
  onboarding, evitando que a mutação válida da primeira tentativa contamine a repetição.

## Evidências do banco real

O ciclo oficial foi executado em PostgreSQL 17.10:

1. downgrade de `20260717_0002` para `20260716_0001`;
2. downgrade de `20260716_0001` até `base`;
3. comprovação de remoção das 23 tabelas da fase;
4. upgrade `base -> 20260716_0001 -> 20260717_0002`;
5. segundo `upgrade head` idempotente;
6. `alembic current` e `alembic heads` em `20260717_0002`.

Inspeção do catálogo após o upgrade:

- papel de aplicação sem `SUPERUSER`, `CREATEROLE`, `CREATEDB` ou `BYPASSRLS`;
- 14 tabelas protegidas com RLS habilitado e forçado;
- 14 políticas RLS;
- 5 triggers de proteção/auditoria;
- 8 constraints compostas que impedem referências entre tenants/empresas;
- todas as 24 tabelas do schema `public` pertencem ao administrador, não ao papel da aplicação;
- índice parcial de convite pendente presente.

Como o Docker local ficou indisponível, a integração usou PostgreSQL oficial portátil e
Memurai Developer 4.1.8 como servidor de protocolo Redis local. O CI continua configurado com
as imagens oficiais `postgres:17-alpine` e `redis:8-alpine`.

## Matriz de validação

| Gate | Resultado observado |
| --- | --- |
| Ruff lint, incluindo regras `S` e `ASYNC` | aprovado |
| Ruff format | 127 arquivos formatados |
| MyPy `strict` | 93 arquivos, zero erro |
| Testes Python unitários | 81 aprovados, 18 de integração desmarcados |
| Testes Python de integração | 18 aprovados |
| Ciclo real de migrações | aprovado até `20260717_0002` |
| OpenAPI | 48 paths, nenhum drift |
| ESLint e Prettier | aprovados |
| TypeScript | aprovado |
| Vitest | 8 arquivos e 22 testes aprovados |
| Cobertura web | 80,45% statements; 59,00% branches; 78,18% functions; 83,58% lines |
| Next.js production build | aprovado; 30 páginas estáticas |
| Playwright collection | 4 testes coletados |
| Playwright real-stack local | bloqueado pelo Docker |
| Docker Compose smoke local | bloqueado pelo Docker |

## Segurança e cadeia de dependências

- `pip-audit`: nenhuma vulnerabilidade conhecida nas dependências publicadas; os pacotes
  editáveis locais `pharma-api` e `pharma-worker` não existem no PyPI e foram explicitamente
  ignorados pela ferramenta.
- SBOM Python CycloneDX:
  `docs/audits/phase2-2a2-python-sbom.cdx.json`, SHA-256
  `3181ED1B1B885A6CB5086E21958EF46A8BFD31CCBECE4D3505BCCA2E32089BF5`.
- `npm audit --audit-level=high`: zero High/Critical; duas ocorrências Moderate herdadas do
  PostCSS incluído pelo Next.js 16.2.10.
- `npm audit fix --force` propôs downgrade destrutivo para Next.js 9.3.3 e não foi aplicado.
- Trivy filesystem (`vuln,misconfig,secret`, severidades High/Critical): zero vulnerabilidade
  no lockfile e zero misconfiguration nos três Dockerfiles.
- Gitleaks: histórico completo sem segredo após restringir a allowlist a identificadores de
  fixtures determinísticas e caminhos de teste/patch histórico.

## Riscos residuais e bloqueios

1. O Docker Desktop permanece indisponível com `HCS_E_HYPERV_NOT_INSTALLED`. Portanto build e
   scan das imagens, smoke Compose e Playwright real-stack dependem do CI.
2. O PostCSS transitivo mantém duas ocorrências Moderate. A aplicação não recebe CSS de usuários,
   o que reduz a exposição, mas a atualização deve ser acompanhada quando o Next.js corrigir a
   árvore sem downgrade.
3. A suíte emite aviso de depreciação da integração `httpx`/`starlette.testclient`; não afeta
   o resultado atual, mas deve ser removido em atualização coordenada.
4. A prova de desempenho cobre a eliminação determinística do N+1 e contenção de escrita, não um
   SLA de throughput. Capacidade de produção ainda exige teste de carga no ambiente de staging.
5. O relatório não declara os gates remotos como aprovados antes do resultado do GitHub Actions.

## Reprodutibilidade

Os comandos canônicos permanecem no `Makefile`, `package.json`,
`scripts/test-migrations.sh` e `scripts/smoke-test-compose.sh`. A sequência mínima é:

```text
make lint
make typecheck
pytest apps/api/tests apps/worker/tests -m "not integration"
bash scripts/test-migrations.sh
pytest apps/api/tests/integration -m integration
npm run test:coverage
npm run build
bash scripts/smoke-test-compose.sh
```
