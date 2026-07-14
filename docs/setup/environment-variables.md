# Catálogo de variáveis de ambiente

| Variável | Processo | Obrigatória | Sensível | Padrão local | Finalidade |
|---|---|---:|---:|---|---|
| `APP_NAME` | API/worker | não | não | `Pharma Intelligence SaaS` | Nome do serviço. |
| `APP_ENV` | API/worker | sim em deploy | não | `development` | `development`, `test`, `staging` ou `production`. |
| `APP_DEBUG` | API | não | não | `false` | Debug do framework; é rejeitado quando verdadeiro em produção. |
| `APP_LOG_LEVEL` | API/worker | não | não | `INFO` | Nível de log. |
| `API_V1_PREFIX` | API | não | não | `/api/v1` | Prefixo versionado. |
| `API_CORS_ORIGINS` | API | sim em deploy | não | localhost e 127.0.0.1 | Lista CSV de origens permitidas. Em produção aceita somente HTTPS, sem wildcard ou loopback. |
| `READINESS_TIMEOUT_SECONDS` | API | não | não | `2.0` | Timeout individual de dependências. |
| `POSTGRES_DB` | Compose | sim | não | `pharma` | Banco local. |
| `POSTGRES_USER` | Compose | sim | não | `pharma` | Usuário local. |
| `POSTGRES_PASSWORD` | Compose | sim | **sim** | valor inseguro de desenvolvimento | Senha do banco. |
| `POSTGRES_PORT` | Compose | não | não | `5432` | Porta publicada. |
| `DATABASE_URL` | API/worker/Alembic | sim | **sim** | URL local | DSN `postgresql+psycopg`. Loopback, senha ausente e senha padrão são rejeitados em produção. |
| `REDIS_URL` | API/worker | sim | potencialmente | `redis://redis:6379/0` | Cache e broker. Loopback é rejeitado em produção. |
| `REDIS_PORT` | Compose | não | não | `6379` | Porta publicada. |
| `NEXT_PUBLIC_API_BASE_URL` | Web/browser | sim | não | `http://localhost:8000/api/v1` | Base pública usada pelo cliente HTTP no navegador. Nunca incluir secret. |
| `WEB_PORT` | Compose | não | não | `3000` | Porta publicada. |
| `DRAMATIQ_PROCESSES` | Worker | não | não | `1` | Quantidade de processos Dramatiq. |
| `DRAMATIQ_THREADS` | Worker | não | não | `4` | Threads por processo Dramatiq. |

## Regras de produção

Ao usar `APP_ENV=production`, o processo falha antes de iniciar quando identifica debug ativo, credencial padrão, hosts de loopback ou CORS inseguro. Essa validação é uma proteção adicional e não substitui secret manager, TLS, revisão de infraestrutura ou políticas de rede.

## Regras gerais

- Secrets reais devem vir de um secret manager no ambiente de deploy.
- Não prefixe valores sensíveis com `NEXT_PUBLIC_`.
- Não registre DSNs, tokens ou payloads pessoais em logs.
- `.env.example` contém somente valores locais substituíveis.
