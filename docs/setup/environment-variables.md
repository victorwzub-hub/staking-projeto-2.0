# Catálogo de variáveis de ambiente

Nenhum valor sensível pode ser prefixado com `NEXT_PUBLIC_`. `.env.example` é exclusivo para desenvolvimento.

## Runtime e HTTP

| Variável | Processo | Sensível | Finalidade |
|---|---|---:|---|
| `APP_NAME` | API/worker | não | Nome do serviço. |
| `APP_ENV` | API/worker | não | `development`, `test`, `staging` ou `production`. |
| `APP_DEBUG` | API | não | Debug; proibido em staging/produção. |
| `APP_LOG_LEVEL` | API/worker | não | Nível de log. |
| `API_V1_PREFIX` | API | não | Prefixo REST, padrão `/api/v1`. |
| `API_CORS_ORIGINS` | API | não | CSV de origens exatas; sem wildcard. |
| `FRONTEND_BASE_URL` | API/worker | não | URL absoluta usada em links de e-mail. |
| `READINESS_TIMEOUT_SECONDS` | API | não | Timeout das dependências. |
| `NEXT_PUBLIC_API_BASE_URL` | web/browser | não | Base pública da API, incorporada no build do Next.js. |
| `NEXT_PUBLIC_API_TIMEOUT_MS` | web/browser | não | Timeout global das chamadas da API em milissegundos; padrão `10000`. |

## PostgreSQL e Redis

| Variável | Processo | Sensível | Finalidade |
|---|---|---:|---|
| `DATABASE_URL` | API/worker/testes | sim | DSN da role de aplicação sem `BYPASSRLS`. |
| `MIGRATION_DATABASE_URL` | migrate | sim | DSN administrativo exclusivo para migrations. |
| `DATABASE_APPLICATION_ROLE` | API/testes | não | Role usada pelo contexto RLS. |
| `POSTGRES_*` | Compose | senha: sim | Provisionamento local. |
| `REDIS_URL` | API/worker | potencialmente | Rate limiting, cache e broker. |

## Senha, sessão e tokens

| Variável | Sensível | Finalidade |
|---|---:|---|
| `PASSWORD_MIN_LENGTH` | não | Comprimento mínimo. |
| `ARGON2_TIME_COST` | não | Custo temporal Argon2id. |
| `ARGON2_MEMORY_COST_KIB` | não | Memória Argon2id. |
| `ARGON2_PARALLELISM` | não | Paralelismo Argon2id. |
| `ARGON2_HASH_LEN` | não | Comprimento do hash. |
| `ARGON2_SALT_LEN` | não | Comprimento do salt. |
| `SESSION_TOKEN_PEPPER` | **sim** | HMAC dos tokens de sessão. Mínimo 32 caracteres em deploy. |
| `ONE_TIME_TOKEN_PEPPER` | **sim** | HMAC de verificação, reset e convite. |
| `SESSION_COOKIE_NAME` | não | Nome do cookie HttpOnly. |
| `CSRF_COOKIE_NAME` | não | Nome do cookie de duplo envio. |
| `SESSION_COOKIE_DOMAIN` | não | Domínio opcional. |
| `SESSION_COOKIE_SECURE` | não | Obrigatório em deploy. |
| `SESSION_COOKIE_SAMESITE` | não | `lax`, `strict` ou `none`. |
| `SESSION_TTL_SECONDS` | não | Vida máxima da sessão. |
| `SESSION_IDLE_TIMEOUT_SECONDS` | não | Expiração por inatividade. |
| `EMAIL_VERIFICATION_TTL_SECONDS` | não | Vida do token de verificação. |
| `PASSWORD_RESET_TTL_SECONDS` | não | Vida do token de reset. |
| `INVITATION_TTL_SECONDS` | não | Vida do convite. |

## Rate limiting

| Variável | Finalidade |
|---|---|
| `LOGIN_MAX_ATTEMPTS` | Tentativas antes do bloqueio. |
| `LOGIN_WINDOW_SECONDS` | Janela de observação. |
| `LOGIN_LOCKOUT_SECONDS` | Backoff inicial. |
| `LOGIN_MAX_LOCKOUT_SECONDS` | Limite superior do backoff progressivo. |
| `PUBLIC_AUTH_MAX_REQUESTS` | Limite de ações públicas. |
| `PUBLIC_AUTH_WINDOW_SECONDS` | Janela das ações públicas. |

## E-mail, bootstrap e retenção

| Variável | Sensível | Finalidade |
|---|---:|---|
| `EMAIL_BACKEND` | não | `development` ou `test` nesta fase. |
| `EMAIL_FROM_ADDRESS` | não | Remetente lógico. |
| `EMAIL_SPOOL_DIRECTORY` | não | Diretório do adapter local. |
| `BOOTSTRAP_ENABLED` | não | Habilitação explícita e temporária. |
| `BOOTSTRAP_ADMIN_EMAIL` | pessoal | E-mail do primeiro platform admin. |
| `BOOTSTRAP_ADMIN_PASSWORD` | **sim** | Senha fornecida pelo secret manager. |
| `AUDIT_RETENTION_DAYS` | não | Política de retenção da auditoria. |
| `SESSION_RETENTION_DAYS` | não | Retenção de sessões revogadas/expiradas. |
| `DRAMATIQ_PROCESSES` | não | Processos do worker. |
| `DRAMATIQ_THREADS` | não | Threads por processo. |

## Guardas de deploy

Em `staging` e `production`, a aplicação rejeita debug, cookies sem Secure, loopback, frontend/CORS sem HTTPS, senha local e peppers fracos/default. Esses guardas não substituem secret manager, TLS, firewall e revisão de IAM.


## Variáveis públicas do frontend

`NEXT_PUBLIC_API_BASE_URL` e `NEXT_PUBLIC_API_TIMEOUT_MS` são incorporadas ao bundle durante o build do Next.js. Alterar esses valores no Railway exige um novo build/deploy do serviço web; reiniciar um artefato já construído não altera o bundle entregue ao navegador.

No staging Railway, configure exatamente:

```text
Web build:
NEXT_PUBLIC_API_BASE_URL=https://<api-publica>/api/v1
NEXT_PUBLIC_API_TIMEOUT_MS=10000

API runtime:
API_CORS_ORIGINS=https://<web-publico>
FRONTEND_BASE_URL=https://<web-publico>
```
