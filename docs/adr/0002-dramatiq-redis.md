# ADR 0002 — Dramatiq com Redis para jobs assíncronos

- Status: aceito
- Data: 2026-07-14

## Contexto

A fundação exige fila e worker, mas ainda não há workflows complexos, agendamento avançado ou múltiplos brokers.

## Decisão

Usar Dramatiq com Redis. Redis já é necessário para cache e permite um ambiente local com menos componentes.

## Alternativas consideradas

- **Celery:** maduro e amplo, porém traz configuração e superfície operacional maiores para a fase atual.
- **RQ:** simples, mas com menos recursos nativos de middleware e retries estruturados.
- **RabbitMQ:** broker robusto, mas adicionaria outro serviço sem necessidade concreta.

## Consequências

A solução possui retries e filas nomeadas com baixa complexidade. Agendamento, dead-letter operacional e políticas avançadas serão adicionados quando surgirem jobs de negócio. Caso os requisitos superem o Dramatiq, a camada de aplicação deverá manter abstrações para migração controlada.
