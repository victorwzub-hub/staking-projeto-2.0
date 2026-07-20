# Contrato OpenAPI

`phase2-openapi.json` é gerado diretamente por `scripts/generate-openapi.py` a partir da aplicação FastAPI. Não edite o JSON manualmente.

```bash
.venv/bin/python scripts/generate-openapi.py
git diff --exit-code docs/openapi/phase2-openapi.json
```

O CI regenera o contrato e falha quando endpoints ou schemas foram alterados sem atualização do arquivo versionado. A documentação interativa continua disponível em `/docs` e `/redoc` fora de produção.
