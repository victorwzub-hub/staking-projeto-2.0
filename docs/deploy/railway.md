# Deploy no Railway

## Topologia

Manter serviços separados: `api`, `web`, `worker`, PostgreSQL e Redis. Somente API e web recebem domínios públicos. Worker, PostgreSQL e Redis usam rede privada e não expõem porta pública.

O Railway não executa `docker-compose.yml` diretamente em produção; cada serviço do Compose deve ser mapeado para um serviço Railway. Os três arquivos de configuração ficam em:

- `/infra/railway/api.railway.json`;
- `/infra/railway/web.railway.json`;
- `/infra/railway/worker.railway.json`.

Em cada serviço, configure o caminho absoluto do arquivo de Config as Code. Os Dockerfiles permanecem relativos à raiz do repositório.

## API

- Dockerfile: `infra/docker/api.Dockerfile`;
- start: imagem usa `${PORT:-8000}`;
- healthcheck: `/api/v1/health`;
- pre-deploy: `DATABASE_URL="$MIGRATION_DATABASE_URL" pharma-migrate`;
- `DATABASE_URL`: credencial da role comum sem `BYPASSRLS`;
- `MIGRATION_DATABASE_URL`: credencial administrativa apenas para migrations;
- `DATABASE_APPLICATION_ROLE`: nome da role comum que receberá grants mínimos.

O pre-deploy precisa terminar com sucesso antes de o novo container receber tráfego. Habilite também **Wait for CI** nos serviços vinculados ao GitHub para impedir deploy de commits cujo workflow falhou.

## Web

- Dockerfile: `infra/docker/web.Dockerfile`;
- `NEXT_PUBLIC_API_BASE_URL=https://<api-publica>/api/v1` precisa existir durante o build;
- `NEXT_PUBLIC_API_TIMEOUT_MS=10000` é validado e também incorporado durante o build;
- alterar qualquer variável `NEXT_PUBLIC_*` exige novo build/deploy; apenas reiniciar o container não atualiza o bundle;
- healthcheck: `/`;
- `PORT` é lido pelo servidor standalone do Next.js.

## Worker

- Dockerfile: `infra/docker/worker.Dockerfile`;
- sem domínio público;
- usa a mesma `DATABASE_URL` de aplicação e `REDIS_URL` privada;
- não executa migrations;
- deploy do worker deve ocorrer somente depois do CI verde e da migration da API concluída.

## Variáveis mínimas

API/worker:

- `APP_ENV=staging`;
- `APP_DEBUG=false`;
- `DATABASE_URL`;
- `MIGRATION_DATABASE_URL` somente na API/pre-deploy;
- `DATABASE_APPLICATION_ROLE`;
- `REDIS_URL`;
- `SESSION_TOKEN_PEPPER` e `ONE_TIME_TOKEN_PEPPER` com 32+ caracteres;
- `SESSION_COOKIE_SECURE=true`;
- `SESSION_COOKIE_SAMESITE`;
- `SESSION_COOKIE_DOMAIN`, quando realmente necessário;
- `API_CORS_ORIGINS=https://<web-publico>` com a origem HTTPS exata, sem wildcard;
- `FRONTEND_BASE_URL=https://<web-publico>`;
- configurações de Argon2, sessão, rate limiting, e-mail e logging.

Web:

- `NEXT_PUBLIC_API_BASE_URL=https://<api-publica>/api/v1`;
- `NEXT_PUBLIC_API_TIMEOUT_MS=10000`.

Esses valores são build-time. Uma alteração exige novo build do serviço web e não apenas restart.

Bootstrap temporário:

- `BOOTSTRAP_ENABLED=true`;
- `BOOTSTRAP_ADMIN_EMAIL`;
- `BOOTSTRAP_ADMIN_PASSWORD`.

Remova/desabilite as variáveis de bootstrap imediatamente após a criação idempotente do primeiro administrador.

## Sequência de staging

1. criar PostgreSQL e Redis gerenciados;
2. criar a role de aplicação sem `SUPERUSER`, `CREATEROLE` ou `BYPASSRLS`;
3. configurar as variáveis por serviço e referências privadas;
4. configurar os caminhos absolutos dos três arquivos Railway;
5. habilitar Wait for CI;
6. implantar API e exigir pre-deploy/migration verde;
7. implantar worker e web;
8. executar bootstrap explícito do primeiro platform admin;
9. validar health, readiness, cookies, CORS, login, onboarding, RLS, worker e logs;
10. desabilitar bootstrap;
11. executar Playwright real e registrar o commit/deployment aprovado.

## Rollback

- rollback de aplicação: selecionar o deployment anterior somente quando a migration for compatível;
- rollback de schema: executar `alembic downgrade <revision>` apenas após análise de perda de dados;
- mudanças destrutivas futuras devem usar expansão/contração;
- falha de migration deve bloquear o deploy, mantendo a versão anterior ativa.

## Estado desta execução

Os arquivos e comandos foram preparados, mas nenhum serviço Railway foi acessado. Sem projeto, credenciais e logs reais, staging permanece não validado.
