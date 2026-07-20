# Benchmark analítico — Etapa 2C

## Protocolo reproduzível

O script `scripts/benchmark-analytics.py` separa geração determinística, agregação diária, transformação semântica, cálculo de KPIs, recomputação idempotente e acesso a cache. Perfis: `smoke=2.000`, `local=50.000` e `staging=1.000.000` fatos sintéticos.

```bash
python scripts/benchmark-analytics.py --profile local
python scripts/benchmark-analytics.py --profile staging --output .local/bench/phase2c-1m.json
python scripts/benchmark-analytics.py --profile local \
  --database-url "$BENCHMARK_DATABASE_URL" --tenant-id "$TENANT_ID"
```

Sem `--database-url`, o resultado mede somente algoritmos sintéticos em memória. Com banco e tenant, mede separadamente uma consulta RLS real, cold/warm no processo, plano/buffers e tamanho das tabelas. O JSON registra versão, data, seed, hash, CPU, parede, pico de alocação Python, linhas e resultados de KPI.

## Critérios

- recomputação deve ser idêntica em 100% das execuções;
- o perfil smoke é gate funcional do CI, não teste de capacidade;
- perfil de 1 milhão deve rodar em staging com CPU/RSS do worker e I/O do PostgreSQL observados externamente;
- consulta real deve ser avaliada com dados e distribuição representativos, cache frio e quente;
- comparar versões exige mesma seed, quantidade, hardware, runtime e configuração do banco.

## SLOs candidatos

Até existirem amostras real-stack de staging, estes são objetivos de engenharia, não resultados comprovados:

- p95 de leitura de KPI em cache: 300 ms;
- p95 de leitura agregada sem cache, janela de dois anos: 2 s;
- refresh incremental de 100 mil fatos: 10 min;
- backfill de 1 milhão de fatos: 60 min e até 1 GiB RSS por worker;
- freshness analítica após lote canônico: 30 min;
- disponibilidade mensal da API analítica: 99,9%;
- recomputação idempotente e isolamento cross-tenant: 100%.

## Resultado local

Executado em 2026-07-18 no perfil `local`, Python 3.12 em Windows, com 50.000 fatos determinísticos e hash `e6e37581…6801579`:

| Estágio | Tempo de parede | Resultado |
|---|---:|---|
| gerador | 1,028 s | 48.615 fatos/s |
| agregação diária | 0,928 s | 50.000 fatos → 14.600 linhas |
| transformação semântica | 0,130 s | snapshot derivado |
| seis KPIs | 0,000152 s | resultados determinísticos |
| recomputação | 0,858 s | idêntica: sim |
| cache em memória | ≤ 0,000002 s | leitura igual à escrita |

Pico `tracemalloc`: 155,402 MiB, que mede alocações Python rastreadas, não RSS total. Esta execução **não** mediu PostgreSQL, RLS, Redis de rede, worker/Dramatiq, API HTTP ou containers; portanto não comprova os SLOs candidatos. A integração real em PostgreSQL e Redis é coberta pelos testes, enquanto capacidade de 1 milhão e percentis real-stack permanecem gate de staging. O JSON bruto fica em `.local/bench/phase2c.json` e não é versionado por conter características da máquina.
