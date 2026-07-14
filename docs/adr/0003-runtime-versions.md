# ADR 0003 — Padronização das versões de runtime

- Status: aceito
- Data: 2026-07-14

## Contexto

A entrega inicial declarava compatibilidade com Python 3.12 e 3.13, enquanto Docker e CI utilizavam Python 3.13. O frontend aceitava Node.js 20.9+, mas os containers e o ambiente real utilizavam Node.js 22. Além disso, `@types/node` estava na linha 26, divergente do runtime.

Essa combinação ampliava a matriz de compatibilidade sem benefício para a fundação e permitia diferenças entre desenvolvimento, imagens e integração contínua.

## Decisão

Padronizar:

- Python 3.12 para desenvolvimento, Docker e GitHub Actions;
- Node.js 22 para desenvolvimento, Docker e GitHub Actions;
- npm 10;
- `@types/node` 22;
- `.python-version` e `.nvmrc` como arquivos de descoberta local.

Os pacotes Python mantêm `requires-python = ">=3.12"`, mas a versão de referência e validação do projeto é 3.12. O CI é o gate autoritativo dessa versão.

## Consequências

### Positivas

- Menor variação entre ambientes.
- Reproduções locais mais previsíveis.
- Tipos Node alinhados às APIs disponíveis no runtime.
- Docker e CI validam a mesma versão alvo definida por Ruff e MyPy.

### Limitações

O ambiente usado para produzir a Fase 1.1 disponibiliza apenas Python 3.13.5. Os testes locais foram executados nessa versão, enquanto a validação em Python 3.12 permanece delegada ao job `backend` do GitHub Actions.

## Alternativas rejeitadas

- **Adotar Python 3.13 como padrão:** rejeitado por ampliar desnecessariamente a diferença em relação à estratégia preferencial solicitada.
- **Manter suporte indiferenciado a várias versões:** rejeitado porque aumentaria a matriz de testes antes de existir uma necessidade de produto.
