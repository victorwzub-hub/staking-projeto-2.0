# PROMPT MESTRE DE IMPLEMENTAÇÃO — FASE 2
# IDENTIDADE, AUTENTICAÇÃO, MULTI-TENANCY, EMPRESAS, FILIAIS,
# USUÁRIOS, RBAC, ONBOARDING, SESSÕES E AUDITORIA

Atue simultaneamente como:

- Principal Software Engineer;
- Staff Software Engineer;
- Arquiteto de Software;
- Arquiteto de Dados;
- Engenheiro de Segurança;
- Especialista em autenticação e autorização;
- Engenheiro DevOps/SRE;
- Especialista em PostgreSQL;
- Especialista em FastAPI;
- Especialista em Next.js e React;
- Product Manager de SaaS B2B;
- UX Designer de sistemas empresariais;
- CTO responsável por um SaaS comercial de alta criticidade.

Estou fornecendo o repositório atualizado do projeto:

Pharma Intelligence SaaS.

A Fase 1 já estabeleceu e validou a fundação técnica:

- monorepo;
- Python 3.12;
- FastAPI;
- SQLAlchemy assíncrono;
- Alembic preparado;
- PostgreSQL;
- Redis;
- Dramatiq;
- Next.js;
- React;
- TypeScript strict;
- Dockerfiles;
- Docker Compose;
- GitHub Actions;
- health check;
- readiness check;
- logs estruturados;
- correlation ID;
- testes backend;
- testes frontend;
- Playwright;
- staging no Railway;
- API, web e worker implantados;
- PostgreSQL e Redis conectados;
- worker consumindo tarefas;
- CORS validado;
- frontend consumindo a API real.

O produto não é um MVP, protótipo, demonstração ou prova de conceito.

A implementação desta fase deve possuir qualidade compatível com um SaaS
comercial completo, seguro, auditável, multi-tenant e preparado para evolução
de longo prazo.

======================================================================
1. MISSÃO DESTA FASE
======================================================================

Implemente exclusivamente a:

FASE 2 — NÚCLEO DE IDENTIDADE, SEGURANÇA E MULTI-TENANCY.

Esta fase deverá entregar um módulo vertical completo contendo:

- identidade global de usuários;
- autenticação;
- sessões;
- segurança da conta;
- grupos econômicos;
- tenants;
- empresas;
- filiais;
- memberships;
- equipes;
- papéis;
- permissões;
- RBAC;
- isolamento entre tenants;
- onboarding;
- convites;
- consentimentos;
- auditoria;
- administração da plataforma;
- frontend completo;
- backend completo;
- migrations;
- testes;
- observabilidade;
- documentação;
- deploy em staging.

Não entregue somente modelos, endpoints isolados, telas estáticas ou
documentação conceitual.

Cada fluxo deve funcionar de ponta a ponta:

banco → backend → autorização → frontend → testes → auditoria →
documentação → deploy.

======================================================================
2. BLOQUEIO DE ESCOPO
======================================================================

Não implemente nesta fase:

- integrações com ERP;
- importação de CSV ou Excel;
- produtos;
- categorias;
- laboratórios;
- fornecedores;
- clientes;
- vendas;
- compras;
- estoque;
- movimentações;
- lotes;
- validade;
- financeiro;
- fluxo de caixa;
- DRE;
- KPIs farmacêuticos;
- diagnósticos;
- recomendações;
- planos de ação;
- billing real;
- Stripe;
- Asaas;
- Machine Learning;
- LLM;
- RAG;
- simuladores;
- dashboards analíticos de negócio;
- previsão de demanda;
- campanhas;
- CRM.

Crie somente os pontos de extensão estritamente necessários para que esses
módulos possam utilizar identidade, tenancy e autorização no futuro.

Não antecipe tabelas e funcionalidades de fases posteriores sem necessidade
arquitetural comprovada.

======================================================================
3. REGRAS ABSOLUTAS DE EXECUÇÃO
======================================================================

1. Não recrie o projeto do zero.

2. Não substitua tecnologias existentes sem justificativa crítica e um ADR.

3. Preserve todas as funcionalidades, testes, Dockerfiles e configurações
   corretas da Fase 1.

4. Antes de modificar o código:

   - inspecione todo o repositório;
   - execute os testes existentes;
   - registre o estado inicial;
   - identifique riscos;
   - identifique dívidas reais;
   - confira o histórico de migrations;
   - confira os workflows;
   - confira os Dockerfiles;
   - confira o staging Railway;
   - confirme a versão real das dependências.

5. Não declare que algo funciona sem executar o teste correspondente.

6. Não desative testes para conseguir aprovação.

7. Não diminua thresholds, regras de lint ou verificações de segurança para
   fazer o pipeline passar.

8. Não use mocks para substituir testes de integração que precisam comprovar
   PostgreSQL, Redis, cookies, RLS ou isolamento entre tenants.

9. Não use SQLite para testes de comportamento específico do PostgreSQL.

10. Não use dados de produção.

11. Não coloque secrets, senhas, tokens ou credenciais no código, nos testes,
    nos logs ou na documentação.

12. Faça perguntas somente quando existir um bloqueio que impeça qualquer
    implementação segura.

13. Para dúvidas não críticas:

    - faça uma suposição tecnicamente razoável;
    - registre a suposição;
    - continue a implementação.

14. Não use `npm audit fix --force`.

15. Não faça downgrade do Next.js.

16. Não atualize para versão canary, beta ou preview sem autorização explícita.

17. O risco moderado conhecido do PostCSS deverá permanecer documentado.
    Não permita CSS arbitrário enviado por usuários.

18. Não adicione o ZIP final dentro do repositório.

19. Não gere o ZIP a partir de uma árvore Git suja.

20. Não considere a fase concluída enquanto existir P0 ou P1 aberto.

======================================================================
4. EXECUÇÃO EM SUBFASES OBRIGATÓRIAS
======================================================================

Execute a Fase 2 na seguinte ordem.

Não comece uma subfase antes de a anterior passar em seus testes essenciais.

----------------------------------------------------------------------
SUBFASE 2.0 — INSPEÇÃO E CONTRATO ARQUITETURAL
----------------------------------------------------------------------

Antes de implementar:

1. descreva o estado atual do projeto;
2. liste os arquivos e módulos existentes;
3. execute os gates atuais;
4. identifique riscos de regressão;
5. confirme o modelo de deploy;
6. confirme a comunicação entre API, web, worker, PostgreSQL e Redis;
7. produza um plano de implementação;
8. registre ADRs antes das decisões estruturais.

Crie ADRs para, no mínimo:

- estratégia de autenticação;
- estratégia de sessão;
- modelo multi-tenant;
- uso de PostgreSQL RLS;
- modelo de RBAC e escopos;
- estratégia de auditoria;
- estratégia de e-mail;
- estratégia de migrations no Railway;
- estratégia de bootstrap do primeiro administrador;
- proteção CSRF e cookies;
- retenção e exclusão de dados de identidade.

Compare objetivamente:

- sessão opaca no servidor;
- JWT;
- access token + refresh token;
- cookies;
- armazenamento de sessão em PostgreSQL;
- cache de sessão em Redis.

Prefira sessões opacas controladas pelo servidor para a aplicação web,
a menos que uma alternativa seja comprovadamente superior para este projeto.

Não use JWT apenas por popularidade.

----------------------------------------------------------------------
SUBFASE 2.1 — MODELAGEM E MIGRATIONS
----------------------------------------------------------------------

Implemente migrations Alembic executáveis e reversíveis.

Crie, no mínimo, as entidades abaixo.

### Identidade global

- users;
- user_profiles;
- user_email_addresses, caso múltiplos e-mails sejam necessários;
- email_verification_tokens;
- password_reset_tokens;
- sessions;
- session_events ou security_events;
- authentication_attempts, quando tecnicamente necessário.

### Estrutura organizacional

- economic_groups;
- tenants;
- companies;
- branches;
- memberships;
- teams;
- team_memberships.

### Autorização

- permissions;
- roles;
- role_permissions;
- role_assignments ou estrutura equivalente;
- system roles;
- custom roles.

### Operação

- invitations;
- terms_versions;
- consent_records;
- onboarding_progress;
- audit_events;
- impersonation_sessions, caso impersonation seja implementada.

Defina claramente:

- finalidade de cada tabela;
- chaves primárias;
- chaves estrangeiras;
- índices;
- unique constraints;
- check constraints;
- tenant_id;
- company_id;
- branch_id;
- created_at;
- updated_at;
- deleted_at somente quando realmente necessário;
- status;
- versionamento otimista;
- retenção;
- anonimização;
- cascatas;
- comportamento de exclusão.

Regras obrigatórias:

1. `users` representa uma identidade global.

2. Um usuário pode participar de mais de um tenant por meio de memberships.

3. `tenant_id` é a principal fronteira de isolamento de dados.

4. Empresas pertencem a um tenant.

5. Filiais pertencem a uma empresa e ao mesmo tenant.

6. Uma membership deve possuir estado explícito:

   - pending;
   - active;
   - suspended;
   - revoked.

7. Papéis e permissões devem permitir escopo:

   - plataforma;
   - tenant;
   - empresa;
   - filial.

8. Papéis do sistema não podem ser editados ou excluídos indevidamente.

9. Papéis personalizados devem pertencer a um tenant.

10. Não utilize relacionamentos polimórficos frágeis sem constraints
    verificáveis.

11. Tokens devem ser armazenados somente como hashes seguros.

12. E-mails devem ser normalizados de forma consistente.

13. E-mail global duplicado deve ser tratado de forma segura e previsível.

14. Migrations devem possuir `upgrade` e `downgrade`.

15. Teste:

    - upgrade em banco vazio;
    - downgrade;
    - novo upgrade;
    - execução em banco já atualizado;
    - constraints;
    - índices;
    - isolamento.

A primeira migration real deverá ser uma base consistente, e não uma sequência
desnecessária de correções criadas durante a mesma execução.

----------------------------------------------------------------------
SUBFASE 2.2 — AUTENTICAÇÃO E SESSÕES
----------------------------------------------------------------------

Implemente fluxos completos para:

- cadastro;
- verificação de e-mail;
- reenvio da verificação;
- login;
- logout;
- logout de todas as sessões;
- recuperação de senha;
- redefinição de senha;
- troca de senha autenticada;
- sessão atual;
- listagem de sessões;
- encerramento de uma sessão específica;
- revogação de sessões;
- expiração;
- bloqueio contra força bruta;
- rate limiting;
- registro de eventos de segurança.

Requisitos obrigatórios:

- Argon2id para hash de senha;
- parâmetros de hash configuráveis;
- rehash automático quando necessário;
- comparação em tempo constante;
- mensagens seguras contra enumeração de e-mail;
- tokens aleatórios criptograficamente seguros;
- tokens de uso único;
- tokens com expiração;
- tokens armazenados somente como hash;
- rotação e revogação;
- proteção contra reutilização;
- sessões por dispositivo;
- IP e user agent tratados de forma segura;
- nenhuma senha ou token em log;
- respostas de recuperação de senha indistinguíveis;
- limite de tentativas;
- backoff progressivo;
- auditoria de sucesso e falha.

A estratégia de cookies deverá documentar e implementar:

- HttpOnly;
- Secure;
- SameSite;
- domínio;
- path;
- tempo de vida;
- renovação;
- revogação;
- CORS com credentials;
- proteção CSRF.

A implementação deverá funcionar:

- localmente;
- em testes;
- em Docker Compose;
- no staging Railway;
- com frontend e API em domínios configuráveis.

Não armazene credenciais permanentes em localStorage.

Não exponha token de sessão ao JavaScript sem necessidade inevitável e
documentada.

----------------------------------------------------------------------
SUBFASE 2.3 — MULTI-TENANCY E RLS
----------------------------------------------------------------------

Implemente isolamento em defesa em profundidade.

O isolamento não poderá depender apenas de filtros adicionados manualmente
em cada endpoint.

Implemente:

1. contexto autenticado;
2. contexto de tenant;
3. contexto opcional de empresa;
4. contexto opcional de filial;
5. autorização na camada de aplicação;
6. filtros de tenant nos repositórios;
7. PostgreSQL Row-Level Security;
8. testes negativos;
9. auditoria de acessos negados.

O tenant ativo deve ser derivado de:

- sessão válida;
- membership válida;
- contexto ativo previamente autorizado.

Não aceite `X-Tenant-ID` enviado pelo navegador como fonte de confiança.

Caso exista troca de tenant, empresa ou filial:

1. o usuário solicita a troca;
2. o backend verifica membership e escopo;
3. o backend atualiza o contexto seguro da sessão;
4. o backend registra auditoria;
5. somente então o novo contexto passa a ser usado.

Para PostgreSQL RLS:

- utilize contexto transacional seguro;
- use `SET LOCAL` ou alternativa equivalente;
- impeça vazamento entre conexões do pool;
- restaure o estado da conexão;
- teste reutilização de conexão;
- teste falhas de transação;
- teste worker e jobs;
- teste platform admin;
- não conceda bypass de RLS à aplicação comum.

Crie testes comprovando que:

- tenant A não lê tenant B;
- tenant A não altera tenant B;
- IDs não podem ser enumerados;
- filial de outra empresa não pode ser acessada;
- membership suspensa não acessa;
- membership revogada não acessa;
- usuário sem membership não acessa;
- troca manual de UUID falha;
- papel removido perde acesso imediatamente;
- conexão reutilizada não mantém tenant anterior;
- jobs assíncronos não executam sem tenant explícito;
- mensagens de erro não revelam existência de recurso de outro tenant.

----------------------------------------------------------------------
SUBFASE 2.4 — RBAC E PERMISSÕES
----------------------------------------------------------------------

Implemente autorização deny-by-default.

Crie um catálogo versionado de permissões.

Inclua, no mínimo, papéis iniciais:

- platform_admin;
- tenant_owner;
- tenant_admin;
- company_admin;
- branch_manager;
- analyst;
- consultant;
- accountant;
- viewer.

Não baseie autorização apenas no nome do papel.

Endpoints devem verificar permissões específicas, por exemplo:

- tenant.read;
- tenant.update;
- company.create;
- company.read;
- company.update;
- company.delete;
- branch.create;
- branch.read;
- branch.update;
- branch.delete;
- user.invite;
- user.read;
- user.update;
- membership.manage;
- role.create;
- role.read;
- role.update;
- role.delete;
- audit.read;
- session.manage;
- impersonation.start.

Implemente:

- papéis do sistema;
- papéis personalizados;
- permissões por papel;
- atribuições por membership;
- escopo por tenant;
- escopo por empresa;
- escopo por filial;
- validação no backend;
- cache seguro de permissões, se necessário;
- invalidação imediata após mudança;
- menor privilégio;
- auditoria.

Não permita:

- editar permissões de platform_admin por API comum;
- excluir o último tenant_owner;
- remover a própria última permissão administrativa sem confirmação;
- elevar privilégios por manipulação de payload;
- atribuir papel acima do próprio escopo;
- criar papel com permissão que o ator não pode delegar.

----------------------------------------------------------------------
SUBFASE 2.5 — ORGANIZAÇÕES E ONBOARDING
----------------------------------------------------------------------

Implemente CRUD autorizado para:

- tenant;
- grupo econômico;
- empresa;
- filial;
- usuários do tenant;
- memberships;
- equipes;
- convites;
- papéis;
- permissões.

Implemente onboarding completo, retomável e idempotente:

1. criação da conta;
2. confirmação do e-mail;
3. criação do tenant;
4. criação opcional do grupo econômico;
5. criação da empresa;
6. criação da primeira filial;
7. criação da membership do proprietário;
8. aplicação do papel tenant_owner;
9. aceite de termos versionados;
10. conclusão;
11. acesso ao painel.

O onboarding deverá:

- salvar progresso;
- permitir retomada;
- impedir duplicidade;
- tolerar reenvio;
- ter idempotência;
- registrar auditoria;
- tratar erros;
- nunca deixar tenant parcialmente configurado sem estado conhecido.

Implemente convites:

- geração segura;
- expiração;
- revogação;
- reenvio;
- aceite;
- associação ao e-mail correto;
- papel e escopo previamente autorizados;
- proteção contra reutilização;
- proteção contra enumeração;
- auditoria.

----------------------------------------------------------------------
SUBFASE 2.6 — FRONTEND
----------------------------------------------------------------------

Implemente uma experiência B2B profissional e responsiva.

Crie páginas para:

- login;
- cadastro;
- verificação de e-mail;
- reenviar verificação;
- esqueci minha senha;
- redefinição de senha;
- onboarding;
- seleção de tenant;
- seleção de empresa;
- seleção de filial;
- perfil;
- troca de senha;
- segurança da conta;
- sessões ativas;
- usuários;
- convites;
- equipes;
- papéis;
- permissões;
- empresas;
- filiais;
- auditoria;
- acesso negado;
- sessão expirada;
- erro inesperado;
- impersonation ativa, caso implementada.

Todos os fluxos devem incluir:

- loading;
- skeleton;
- empty state;
- validação;
- tratamento de erro;
- mensagens acessíveis;
- foco correto;
- teclado;
- responsividade;
- confirmação de ações destrutivas;
- proteção contra dupla submissão;
- retry;
- redirecionamento seguro;
- tratamento de sessão expirada;
- tratamento de acesso revogado;
- proteção de rotas.

Não crie apenas telas estáticas.

As páginas devem consumir os endpoints reais.

Use componentes reutilizáveis.

Não esconda erros de autorização.

Não use o frontend como única camada de segurança.

----------------------------------------------------------------------
SUBFASE 2.7 — AUDITORIA E SEGURANÇA OPERACIONAL
----------------------------------------------------------------------

Implemente auditoria para:

- cadastro;
- verificação de e-mail;
- login;
- falha de login;
- logout;
- recuperação de senha;
- troca de senha;
- sessão criada;
- sessão revogada;
- sessão expirada;
- tenant criado;
- empresa criada ou alterada;
- filial criada ou alterada;
- convite criado;
- convite aceito;
- membership alterada;
- papel atribuído;
- papel removido;
- permissão alterada;
- acesso negado;
- mudança de contexto;
- impersonation;
- alteração administrativa.

Cada evento deve registrar, quando aplicável:

- actor_user_id;
- effective_user_id;
- tenant_id;
- company_id;
- branch_id;
- ação;
- categoria;
- recurso;
- resource_id;
- resultado;
- correlation_id;
- timestamp;
- IP minimizado ou tratado;
- user agent;
- campos alterados;
- justificativa;
- metadata segura.

Não registre:

- senha;
- token;
- cookie;
- segredo;
- hash de senha;
- credencial de integração;
- payload sensível completo.

A auditoria deverá ser append-only.

Impeça update e delete comuns na tabela de auditoria.

Documente retenção e exportação.

----------------------------------------------------------------------
SUBFASE 2.8 — E-MAIL E WORKER
----------------------------------------------------------------------

Crie abstração independente de provedor para:

- verificação de e-mail;
- recuperação de senha;
- convites;
- notificações de segurança.

Implemente:

- interface;
- serviço;
- adapter de desenvolvimento;
- adapter de teste;
- templates;
- filas;
- retries;
- backoff;
- idempotência;
- logs;
- métricas;
- testes.

Sem credenciais reais, utilize um provedor de desenvolvimento seguro que:

- não envie mensagens externamente;
- permita inspecionar o conteúdo nos testes;
- não registre tokens completos em logs.

Prepare documentação para ativar um provedor real posteriormente.

Os atores Dramatiq devem retornar `None`, salvo quando Results Middleware for
realmente necessário.

Não adicione Results Middleware apenas para eliminar um aviso.

----------------------------------------------------------------------
SUBFASE 2.9 — RAILWAY, MIGRATIONS E DEPLOY
----------------------------------------------------------------------

Prepare a imagem da API para conter:

- `alembic.ini`;
- diretório de migrations;
- scripts necessários;
- dependências de runtime.

Implemente uma estratégia segura para migrations no Railway.

Requisitos:

- migrations executadas antes da nova versão receber tráfego;
- apenas um processo executando migrations;
- falha da migration bloqueando o deploy;
- migrations compatíveis com rollback;
- nenhuma migration destrutiva sem estratégia de expansão e contração;
- nenhum seed automático perigoso;
- nenhuma senha padrão;
- nenhum administrador padrão público.

Crie um comando idempotente para bootstrap do primeiro platform_admin.

Esse comando deverá:

- exigir variáveis explícitas;
- nunca possuir senha hardcoded;
- falhar de forma segura;
- não duplicar usuários;
- registrar auditoria;
- poder ser desabilitado depois do bootstrap.

Documente as variáveis do Railway para:

- API;
- web;
- worker;
- PostgreSQL;
- Redis;
- cookies;
- CORS;
- sessão;
- e-mail;
- bootstrap;
- logging.

Preserve a arquitetura atual de serviços separados no Railway:

- api;
- web;
- worker;
- PostgreSQL;
- Redis.

Não exponha PostgreSQL, Redis ou worker publicamente.

----------------------------------------------------------------------
SUBFASE 2.10 — TESTES E QUALITY GATES
----------------------------------------------------------------------

Implemente testes unitários, integração e E2E.

### Backend

Teste:

- modelos;
- serviços;
- repositórios;
- autenticação;
- senha;
- tokens;
- sessões;
- rate limiting;
- convites;
- onboarding;
- RBAC;
- RLS;
- auditoria;
- migrations;
- API;
- cookies;
- CSRF;
- CORS;
- erros;
- concorrência;
- idempotência.

### Multi-tenancy

Crie uma matriz específica de testes com:

- tenant A;
- tenant B;
- empresas distintas;
- filiais distintas;
- usuários com múltiplas memberships;
- memberships suspensas;
- memberships revogadas;
- papéis distintos;
- escopos distintos.

### Frontend

Teste:

- componentes;
- formulários;
- erros;
- loading;
- sessão expirada;
- rotas protegidas;
- onboarding;
- login;
- logout;
- usuários;
- convites;
- papéis;
- empresas;
- filiais.

### E2E

Implemente E2E real para:

1. cadastro;
2. verificação simulada de e-mail;
3. onboarding;
4. criação de empresa;
5. criação de filial;
6. convite;
7. aceite do convite;
8. login;
9. troca de contexto;
10. acesso permitido;
11. acesso negado;
12. logout;
13. recuperação de senha;
14. revogação de sessão;
15. isolamento entre tenants.

Os testes de integração devem usar PostgreSQL e Redis reais.

Não substitua RLS por mock.

Adicione ao CI:

- Ruff;
- Ruff format;
- MyPy strict;
- Pytest;
- cobertura;
- Alembic upgrade;
- Alembic downgrade;
- Alembic upgrade novamente;
- ESLint;
- Prettier;
- TypeScript;
- Vitest;
- build Next.js;
- Playwright;
- Docker Compose smoke;
- npm audit com bloqueio para high e critical;
- pip-audit;
- secret scanning;
- scan de imagens quando operacionalmente adequado.

O risco moderado conhecido do PostCSS deverá permanecer documentado até
existir atualização estável e compatível.

Não permita CSS arbitrário de usuário.

======================================================================
5. CONTRATO DA API
======================================================================

Use APIs REST versionadas em `/api/v1`.

Adote um formato consistente de erros, preferencialmente compatível com
Problem Details.

Implemente, no mínimo, grupos de endpoints para:

- auth;
- sessions;
- me;
- onboarding;
- tenants;
- economic-groups;
- companies;
- branches;
- users;
- memberships;
- teams;
- invitations;
- roles;
- permissions;
- audit-events;
- impersonation, caso implementada.

Inclua:

- schemas Pydantic;
- validação;
- autorização;
- paginação;
- filtros;
- ordenação;
- correlation ID;
- idempotency key quando aplicável;
- rate limiting;
- exemplos OpenAPI;
- respostas padronizadas.

Não retorne dados internos desnecessários.

Não exponha existência de recursos de outro tenant.

======================================================================
6. IMPERSONATION ADMINISTRATIVA
======================================================================

Implemente impersonation somente se todos os controles abaixo forem
entregues:

- permissão específica;
- motivo obrigatório;
- tempo curto;
- expiração;
- encerramento explícito;
- banner visível;
- auditoria do ator real;
- auditoria do usuário representado;
- proibição de ocultação;
- proteção de ações críticas;
- impossibilidade de impersonar platform_admin comum;
- registro do início e do fim.

Caso não seja possível implementar com todos os controles, registre como
pendência futura e não entregue uma versão insegura.

======================================================================
7. OBSERVABILIDADE
======================================================================

Inclua logs estruturados e métricas relevantes para:

- login;
- falha de login;
- bloqueios;
- criação e revogação de sessão;
- tempo de resposta;
- erros de autorização;
- acessos negados;
- convites;
- e-mails;
- filas;
- migrations;
- erros de banco;
- erros de Redis;
- onboarding;
- worker.

Não coloque PII ou secrets em labels de métricas.

Mantenha correlation ID entre API, jobs e auditoria.

======================================================================
8. DOCUMENTAÇÃO OBRIGATÓRIA
======================================================================

Atualize:

- README.md;
- CHANGELOG.md;
- ROADMAP.md;
- SECURITY.md;
- CONTRIBUTING.md;
- catálogo de variáveis;
- documentação de arquitetura;
- ADRs;
- manual de instalação;
- manual de migrations;
- manual do Railway;
- manual de autenticação;
- manual de tenancy;
- manual de RBAC;
- manual de auditoria;
- manual de bootstrap;
- manual do administrador;
- documentação OpenAPI;
- troubleshooting.

Documente claramente:

- como criar o primeiro platform_admin;
- como criar tenant;
- como convidar usuários;
- como criar papéis;
- como verificar isolamento;
- como revogar sessões;
- como executar migrations;
- como fazer rollback;
- como testar;
- como implantar;
- como recuperar de falha.

======================================================================
9. DEFINITION OF DONE
======================================================================

A Fase 2 somente poderá ser considerada concluída quando:

1. migrations estiverem implementadas;
2. migrations subirem em banco vazio;
3. downgrade funcionar;
4. novo upgrade funcionar;
5. autenticação funcionar de ponta a ponta;
6. sessões funcionarem;
7. recuperação de senha funcionar;
8. onboarding funcionar;
9. tenants funcionarem;
10. empresas funcionarem;
11. filiais funcionarem;
12. memberships funcionarem;
13. convites funcionarem;
14. RBAC funcionar;
15. isolamento entre tenants estiver comprovado;
16. RLS estiver ativo e testado;
17. frontend estiver completo;
18. API estiver documentada;
19. auditoria estiver implementada;
20. logs estiverem adequados;
21. worker estiver processando e-mails;
22. testes backend passarem;
23. testes frontend passarem;
24. Playwright passar;
25. Docker Compose smoke passar;
26. GitHub Actions ficar totalmente verde;
27. staging Railway ficar totalmente verde;
28. migrations forem aplicadas no staging;
29. nenhuma credencial estiver versionada;
30. nenhuma vulnerabilidade alta ou crítica estiver aberta;
31. risco moderado do PostCSS permanecer documentado;
32. nenhum P0 ou P1 estiver aberto;
33. documentação estiver atualizada;
34. o Git estiver limpo;
35. o ZIP final for criado a partir do commit aprovado.

======================================================================
10. VALIDAÇÃO OBRIGATÓRIA
======================================================================

Execute e registre os comandos reais.

### Backend

- Ruff;
- Ruff format;
- MyPy strict;
- Pytest;
- cobertura;
- pip check;
- pip-audit;
- Alembic heads;
- Alembic current;
- Alembic upgrade head;
- Alembic downgrade;
- Alembic upgrade novamente.

### Frontend

- npm ci;
- ESLint;
- Prettier;
- TypeScript;
- Vitest;
- coverage;
- Next.js build;
- Playwright;
- npm audit com bloqueio para high e critical.

### Integração

- Docker Compose config;
- build das imagens;
- subida da stack;
- migrations;
- health;
- readiness;
- frontend;
- API;
- Redis;
- PostgreSQL;
- worker;
- tarefa real;
- shutdown;
- nova inicialização;
- idempotência.

### Staging Railway

Valide:

- API;
- web;
- worker;
- PostgreSQL;
- Redis;
- health;
- readiness;
- CORS;
- cookies;
- autenticação;
- onboarding;
- migrations;
- tarefa real;
- fluxo E2E;
- logs;
- reinicialização.

Quando o ambiente não permitir um teste:

- não invente resultado;
- registre como não executado;
- explique por quê;
- forneça o comando exato;
- não declare aprovação enquanto o gate obrigatório estiver pendente.

======================================================================
11. FORMATO DE ENTREGA
======================================================================

Ao final, entregue obrigatoriamente:

### 1. Resumo executivo

- o que foi implementado;
- principais decisões;
- riscos;
- limitações;
- resultado.

### 2. Estado inicial

- estrutura encontrada;
- testes iniciais;
- problemas existentes;
- regressões encontradas.

### 3. Decisões técnicas

Para cada decisão:

- escolha;
- justificativa;
- alternativas;
- riscos;
- impacto;
- ADR correspondente.

### 4. Arquivos modificados

Liste todos os caminhos reais.

### 5. Migrations

Liste:

- revision;
- finalidade;
- upgrade;
- downgrade;
- resultado dos testes.

### 6. Endpoints

Liste:

- método;
- rota;
- permissão;
- escopo;
- entrada;
- saída;
- erros.

### 7. Testes

Informe:

- comando;
- exit code;
- quantidade;
- cobertura;
- resultado.

### 8. Segurança

Informe:

- autenticação;
- tokens;
- cookies;
- CSRF;
- rate limiting;
- RLS;
- RBAC;
- auditoria;
- secrets;
- vulnerabilidades;
- riscos aceitos.

### 9. Staging

Informe:

- serviços;
- migrations;
- health;
- readiness;
- E2E;
- worker;
- logs;
- resultado.

### 10. Pendências reais

Inclua somente:

- dependência externa;
- credencial;
- decisão comercial;
- validação jurídica;
- limitação comprovada.

Não use pendências genéricas.

### 11. Veredito

Use exclusivamente:

FASE 2 APROVADA

ou:

FASE 2 REPROVADA

Não utilize “parcialmente aprovada”.

### 12. ZIP final

Antes de criar o ZIP:

1. execute `git status --porcelain`;
2. confirme que está vazio;
3. confirme o commit final;
4. não adicione o ZIP ao repositório;
5. gere o arquivo fora da raiz do projeto.

Exemplo:

git archive --format=zip --output=../pharma-intelligence-saas-phase2-final.zip HEAD

O ZIP não deve conter:

- node_modules;
- .env;
- secrets;
- caches;
- relatórios temporários;
- bancos locais;
- artefatos de testes;
- o próprio ZIP;
- arquivos não versionados.

======================================================================
12. CRITÉRIO DE EFICIÊNCIA E REDUÇÃO DE RETRABALHO
======================================================================

Durante a implementação:

1. Faça primeiro decisões estruturais e migrations.

2. Não crie frontend antes de os contratos de API estarem estabilizados.

3. Não crie endpoints antes de os modelos e regras de autorização estarem
   definidos.

4. Não deixe RLS para o final.

5. Não deixe migrations e deploy para o final.

6. Não deixe testes multi-tenant para o final.

7. Desenvolva cada capability verticalmente:

   banco → domínio → serviço → repositório → API → autorização →
   frontend → testes → auditoria → documentação.

8. Execute testes incrementais após cada capability.

9. Não acumule dezenas de alterações sem validação.

10. Não altere arquivos fora do escopo sem necessidade comprovada.

11. Não replique lógica de autorização.

12. Centralize regras de tenant e permissionamento.

13. Use factories e fixtures reutilizáveis nos testes.

14. Preserve compatibilidade com as fases seguintes.

15. Sempre que um gate falhar:

    - descubra a causa;
    - corrija a causa;
    - execute novamente o gate;
    - execute novamente todos os gates dependentes.

======================================================================
13. INÍCIO DA EXECUÇÃO
======================================================================

Comece agora pela Subfase 2.0.

Primeiro:

1. inspecione integralmente o repositório;
2. execute os gates atuais;
3. informe o estado encontrado;
4. proponha o plano;
5. crie os ADRs essenciais;
6. implemente as migrations;
7. continue a execução sem interromper por dúvidas não críticas.

Não pare apenas na análise.

Implemente a Fase 2 completa no repositório fornecido.