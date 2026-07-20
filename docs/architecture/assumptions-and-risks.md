# Suposições e riscos

## Suposições

1. O ZIP recebido é um `git archive` da Fase 1.1; o histórico original não estava incluído.
2. Python 3.12, Node 22, PostgreSQL 17 e Redis 8 são oficiais.
3. PostgreSQL e Redis gerenciados serão usados em staging/produção.
4. API, web e worker permanecem serviços separados no Railway.
5. Identidade é global; `tenant_id` é fronteira de dados organizacionais.
6. Sessão web é opaca e server-side; JWT não é necessário.
7. Impersonation permanece adiada até todos os controles do ADR 0014.
8. Termos seedados são técnicos para staging e exigem validação jurídica.

## Riscos e gates

- Docker e serviços nativos não estão disponíveis no ambiente local atual; integração real depende do CI.
- O Python local é 3.13, embora Docker/CI estejam padronizados em 3.12.
- Chromium local bloqueia loopback; Playwright real deve rodar no CI.
- Não há acesso/credenciais Railway nesta execução; deploy e staging não podem ser declarados aprovados.
- RLS somente é comprovado com PostgreSQL real; testes locais coletados não equivalem a execução.
- PostCSS possui risco moderado conhecido; CSS arbitrário de usuário é proibido.
- Requisitos LGPD, retenção e termos exigem validação jurídica antes da operação comercial.
