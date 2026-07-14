# Arquitetura inicial

## Contexto

O produto exige evolução longa, domínio complexo e forte isolamento por tenant. Na fundação, a prioridade é reduzir custo operacional e manter fronteiras internas claras.

## Estilo escolhido

**Monólito modular**, com três processos implantáveis no mesmo repositório:

1. `web`: interface Next.js;
2. `api`: aplicação FastAPI e módulos de domínio;
3. `worker`: execução assíncrona Dramatiq.

PostgreSQL é a fonte transacional. Redis atende cache e broker de jobs. Isso não transforma a solução em microsserviços: API e worker compartilham contratos, configuração e o mesmo modelo de domínio.

## Fronteiras do backend

- `domain`: entidades, regras e contratos sem dependência de framework;
- `application`: casos de uso e orquestração;
- `infrastructure`: banco, cache, mensageria e adapters;
- `api`: transporte HTTP e schemas;
- `core`: configuração, logs e tratamento transversal;
- `middleware`: preocupações do ciclo de requisição.

Nesta fase, somente o módulo operacional de health/readiness existe. Não foram criadas entidades artificiais.

## Fluxo operacional atual

```text
Browser -> Next.js (interface)
Browser -> FastAPI /api/v1/health
FastAPI -> PostgreSQL
FastAPI -> Redis
FastAPI/worker -> Dramatiq via Redis
```

O componente de status executa a chamada no navegador usando `NEXT_PUBLIC_API_BASE_URL`. O health check do container web também consulta a API pelo DNS interno `api`, permitindo detectar quebra de comunicação na rede do Compose.

## Observabilidade preparada

- logs JSON estruturados;
- `X-Correlation-ID` aceito somente quando contém caracteres seguros e até 128 posições;
- UUID gerado para valores ausentes ou inválidos;
- liveness independente de dependências;
- readiness consulta PostgreSQL e Redis com timeout;
- health checks no Docker Compose;
- fechamento explícito das conexões no shutdown.

Tracing, métricas, Sentry, OpenTelemetry e dashboards operacionais permanecem no roadmap; adicioná-los agora geraria configuração sem sinais de negócio úteis.

## Estratégia de evolução

Fronteiras modulares devem ser preservadas. Extração para serviço independente somente será considerada quando houver necessidade mensurável de escala, isolamento operacional, cadência de deploy ou responsabilidade de equipe.
