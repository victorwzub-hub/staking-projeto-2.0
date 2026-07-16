# Visão arquitetural

O projeto adota monólito modular com processos `web`, `api` e `worker`. PostgreSQL é a fonte transacional e de sessão; Redis atende rate limiting, cache efêmero e Dramatiq.

A Fase 2 adiciona o núcleo vertical de identidade e multi-tenancy. Consulte [`phase2-overview.md`](phase2-overview.md) para autenticação, RLS, RBAC, auditoria e deploy.

Extração para microsserviços somente ocorrerá mediante necessidade mensurável de escala, isolamento operacional ou ownership de equipe. Kafka, Kubernetes, ClickHouse e outros componentes não são necessários neste estágio.
