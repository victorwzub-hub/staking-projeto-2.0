# ADR 0001 — Monólito modular como arquitetura inicial

- Status: aceito
- Data: 2026-07-14

## Contexto

O produto terá domínio extenso, mas a Fase 1 não possui carga, equipes independentes ou requisitos que justifiquem microsserviços. A prioridade é velocidade com disciplina arquitetural.

## Decisão

Adotar monólito modular em monorepo, com frontend, API e worker como processos separados, mantendo domínio e persistência compartilhados.

## Alternativas consideradas

- **Microsserviços:** rejeitados nesta fase por custo de rede, contratos distribuídos, observabilidade e deploy.
- **Arquitetura orientada a eventos:** usada apenas internamente para jobs; não como espinha dorsal distribuída.
- **Serverless:** rejeitado como padrão inicial por jobs longos, conexões de banco e portabilidade operacional.
- **Híbrida:** possível no futuro para ingestão ou analytics com demanda comprovada.

## Consequências

Vantagens: menor custo, transações simples, refatoração rápida e testes integrados. Limitações: exige governança de fronteiras e pode demandar extrações futuras. A extração ocorrerá apenas mediante métricas de escala, isolamento ou autonomia de equipe.
