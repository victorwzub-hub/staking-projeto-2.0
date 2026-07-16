# ADR 0011 — Migrations no Railway

- Status: Aceito
- Data: 2026-07-16

## Decisão

Migrations são executadas por comando de release dedicado antes da API receber tráfego. O processo usa PostgreSQL advisory lock para garantir executor único. Falha interrompe o deploy. API e worker nunca executam migrations automaticamente no startup.

A imagem da API inclui `alembic.ini`, diretório `alembic` e scripts. Mudanças destrutivas futuras seguirão expansão/contração. O usuário de runtime não deve possuir DDL em produção.
