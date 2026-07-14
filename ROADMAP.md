# Roadmap

## Fase 1 — Fundação técnica — concluída

- Monorepo, ambiente local, API, frontend, PostgreSQL, Redis e worker.
- Logs estruturados, health checks, readiness e correlation ID.
- Qualidade, testes, build e CI inicial.
- Documentação, segurança básica e ADRs.

## Fase 1.1 — Correção e gate final — implementação concluída

- Frontend conectado ao health check real da API.
- Endpoint raiz e encerramento correto de recursos.
- Docker reproduzível com `npm ci` e runtimes alinhados.
- Proteções contra configuração insegura em produção.
- Correlation ID validado por tamanho e caracteres.
- Serialização defensiva de erros de validação.
- Smoke test completo do Compose e job de CI.
- E2E atualizado para loading e resposta de health.

**Gate ambiental pendente:** o job `compose-smoke` deve passar no GitHub Actions, pois Docker não está disponível no ambiente local desta correção. A Fase 2 não deve ser iniciada antes desse resultado verde.

## Fase 2 — Identidade, tenancy e autorização — próxima após o gate

Objetivo: implementar o primeiro módulo vertical de negócio sem avançar para dashboards ou inteligência analítica.

- Modelagem de tenant, grupo econômico, empresa, filial e usuário.
- Autenticação segura, sessão/token, recuperação de acesso e preparação para MFA.
- RBAC com papéis e permissões granulares.
- Auditoria de eventos de segurança e alterações administrativas.
- Isolamento por tenant, política de acesso e testes contra vazamento cruzado.
- Onboarding mínimo e telas de login, seleção de empresa e filial.
- Migrations, endpoints, frontend, testes de integração e E2E.
- ADR da estratégia multi-tenant e threat model inicial.

## Fase 3 — Plataforma de integrações

- SDK interno de conectores.
- Importação manual CSV/Excel com staging, idempotência e reconciliação.
- Histórico de sincronizações, erros e reprocessamento.

## Fase 4 — Catálogo e pipeline de dados

- Produtos, categorias, fornecedores, vendas, compras, estoque e financeiro.
- Validação, normalização, qualidade e linhagem.

## Fase 5 — KPIs, diagnósticos e planos de ação

- Catálogo versionado de KPIs.
- Motor de regras e evidências rastreáveis.
- Alertas, recomendações e acompanhamento de ações.

## Fases posteriores

- Simuladores, billing, conectores ERP homologados, camada analítica, Machine Learning e LLM controlada.
- Infraestrutura de produção, backup/restore, observabilidade completa, SLOs e testes de carga.
