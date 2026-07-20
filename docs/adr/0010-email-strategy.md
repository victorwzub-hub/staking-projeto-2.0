# ADR 0010 — E-mail e worker

- Status: Aceito
- Data: 2026-07-16

## Decisão

O domínio usa uma interface de entrega de e-mail independente de provedor. API enfileira tarefas Dramatiq no Redis. O adapter de desenvolvimento grava mensagens em diretório local ignorado pelo Git; o adapter de teste mantém mensagens em memória. Nenhuma mensagem é enviada externamente sem configuração explícita.

Tokens completos podem existir apenas no corpo da mensagem de desenvolvimento/teste, nunca em logs. Atores retornam `None`, usam retries/backoff e chave de idempotência.
