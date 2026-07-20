# Troubleshooting

## Readiness 503

Confirme PostgreSQL, Redis, DSNs, role de aplicação e migration atual. Liveness 200 não significa dependências prontas.

## Login retorna 503

O rate limiter é fail-closed. Verifique Redis e seus logs. Não desabilite o limiter como correção.

## Login retorna 429

Aguarde `retry_after_seconds`. Em teste controlado, limpe somente a chave Redis correspondente; nunca faça flush de Redis compartilhado.

## 403 após troca de contexto

Confirme membership `active`, relação empresa/filial e atribuições. Não tente enviar `X-Tenant-ID`; o contexto confiável está na sessão.

## Dados ausentes apesar de existirem

Verifique o contexto RLS da transação, a role sem `BYPASSRLS` e as FKs compostas. Não desative RLS.

## CSRF inválido

Confirme cookie CSRF, header `X-CSRF-Token`, credentials no fetch e CORS exato. Em staging/produção, cookies exigem HTTPS e `Secure=true`.

## E-mail não chegou em desenvolvimento

O adapter não envia externamente. Inspecione `EMAIL_SPOOL_DIRECTORY`. O token completo deve aparecer somente no arquivo de spool, nunca no log.

## Migration falhou

Execute `alembic current`, capture logs, não reinicie API/worker sobre schema incompleto e corrija a causa. Em deploy, a falha deve bloquear tráfego.

## Playwright local bloqueado

Use o Chromium oficial instalado por `npx playwright install --with-deps chromium` ou execute no CI. Não declare o gate aprovado apenas porque os testes foram coletados.
