# Troubleshooting

## Readiness 503

Verifique `DATABASE_URL`, `REDIS_URL`, DNS privado, migrations e privilégios da role da aplicação.

## RLS retorna lista vazia

Confirme sessão ativa, membership `active`, contexto de tenant e que a transação executou `apply_rls_context`. Não desative RLS para corrigir o sintoma.

## 403 CSRF

Confirme cookies, `credentials: include`, origem CORS, `X-CSRF-Token` igual ao cookie CSRF e política Secure/SameSite coerente com os domínios.

## Login 429/503

429 indica limite excedido. 503 indica Redis indisponível e bloqueio fail-closed. Não contorne o limiter.

## E-mail não aparece

Confirme worker, fila `email`, Redis e `EMAIL_SPOOL_DIRECTORY`. Não procure tokens nos logs; inspecione o spool apenas em ambiente seguro.

## Migration lock

`Another migration process holds the deployment lock` indica outro executor. Não force duas migrations simultâneas.

## Papel não produz acesso

Confirme assignment, escopo empresa/filial, contexto ativo e permissões do papel. Remoções têm efeito na requisição seguinte.

## Playwright local bloqueado

Instale Chromium oficial do Playwright. Políticas corporativas de navegador podem bloquear loopback; use runner CI isolado.
