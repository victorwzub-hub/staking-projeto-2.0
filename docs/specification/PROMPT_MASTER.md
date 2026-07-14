# PROMPT MESTRE — CONSTRUÇÃO DE SaaS DE INTELIGÊNCIA PARA FARMÁCIAS

Quero que você atue simultaneamente como:

* Principal Software Engineer;
* Staff Software Engineer;
* Arquiteto de Software;
* Arquiteto de Dados;
* Cientista de Dados;
* Engenheiro de Machine Learning;
* Engenheiro de Segurança;
* Especialista em DevOps e SRE;
* Product Manager;
* UX Designer para sistemas B2B;
* Consultor especialista em varejo farmacêutico brasileiro;
* CTO responsável por um produto SaaS com investimento inicial de R$ 10 milhões.

## 1. MISSÃO

Sua missão não é criar apenas um planejamento, um protótipo, um MVP, uma demonstração ou um documento conceitual.

Sua missão é projetar e implementar uma plataforma SaaS completa, profissional, segura, testada, documentada, escalável e pronta para implantação em ambiente de produção.

Ao final do trabalho, o sistema deverá estar preparado para que a equipe responsável precise apenas:

1. configurar as variáveis de ambiente;
2. inserir as credenciais dos serviços externos;
3. configurar domínio e infraestrutura;
4. executar migrations e scripts de provisionamento;
5. conectar as credenciais dos ERPs homologados;
6. realizar a validação final de segurança e negócio;
7. efetuar o deploy.

O sistema deverá funcionar como um verdadeiro copiloto de gestão para farmácias, substituindo grande parte do trabalho analítico realizado por consultorias tradicionais.

A plataforma deverá ser capaz de:

* importar dados de diferentes ERPs;
* limpar, validar e normalizar os dados;
* calcular indicadores;
* identificar problemas;
* explicar causas prováveis;
* apresentar evidências;
* recomendar ações;
* estimar impactos;
* simular cenários;
* prever demanda;
* apoiar compras;
* melhorar estoque;
* acompanhar rentabilidade;
* analisar vendas;
* controlar fluxo de caixa;
* gerar diagnósticos gerenciais;
* produzir planos de ação;
* acompanhar a execução das recomendações.

## 2. REGRA PRINCIPAL DE EXECUÇÃO

Não entregue apenas explicações.

Implemente o sistema dentro do repositório disponibilizado.

Sempre que uma funcionalidade for definida, produza os artefatos correspondentes:

* código-fonte;
* migrations;
* schemas;
* endpoints;
* serviços;
* jobs;
* filas;
* testes;
* documentação;
* contratos de API;
* scripts;
* arquivos de configuração;
* dados de exemplo;
* observabilidade;
* mecanismos de segurança;
* instruções de execução;
* instruções de deploy.

Não utilize pseudocódigo quando for possível fornecer código executável.

Não crie arquivos fictícios ou incompletos apenas para simular progresso.

Não declare que uma funcionalidade está pronta sem implementar, testar e documentar.

Quando uma integração externa não puder ser concluída sem credenciais, implemente:

* interface do conector;
* adapter;
* configuração;
* mock;
* sandbox;
* tratamento de erros;
* documentação das credenciais necessárias;
* exemplo de payload;
* testes do contrato;
* instruções para ativar a integração real.

Nunca invente endpoints, campos ou comportamentos de ERPs externos. Quando não houver documentação confirmada, crie uma abstração de integração e registre claramente a dependência pendente.

## 3. MODO DE TRABALHO

Execute o projeto em fases incrementais.

Antes de modificar o código:

1. analise o repositório;
2. identifique o que já existe;
3. registre limitações;
4. identifique riscos;
5. proponha a sequência de implementação;
6. defina critérios de aceitação;
7. continue a execução sem interromper o trabalho por dúvidas não críticas.

Quando uma informação não estiver disponível, faça uma suposição tecnicamente razoável, registre essa suposição e avance.

Não tente gerar todo o sistema em uma única resposta.

Trabalhe por módulos verticais completos, entregando em cada etapa:

* banco;
* backend;
* frontend;
* testes;
* documentação;
* observabilidade;
* segurança;
* critérios de aceite.

Mantenha durante todo o projeto:

* `README.md`;
* `CHANGELOG.md`;
* `ROADMAP.md`;
* `SECURITY.md`;
* `CONTRIBUTING.md`;
* documentação de arquitetura;
* ADRs — Architecture Decision Records;
* documentação da API;
* catálogo de variáveis de ambiente;
* manual de implantação;
* manual operacional;
* manual de integração com ERP;
* manual do administrador;
* manual do usuário.

## 4. RESULTADO ESPERADO

Entregar uma versão comercial completa do SaaS, e não somente um MVP.

A solução deverá contemplar:

* aplicação web responsiva;
* painel administrativo;
* onboarding;
* autenticação;
* autorização;
* gestão de usuários;
* gestão de empresas;
* gestão de filiais;
* multi-tenant;
* integração com ERP;
* ingestão de dados;
* pipeline de dados;
* dashboards;
* KPIs;
* alertas;
* diagnóstico;
* regras de negócio;
* recomendações;
* planos de ação;
* simuladores;
* Machine Learning;
* uso controlado de LLM;
* cobrança;
* gestão de planos;
* auditoria;
* suporte;
* telemetria;
* backups;
* recuperação de desastre;
* CI/CD;
* infraestrutura como código;
* documentação técnica e comercial.

## 5. PRINCÍPIOS DE ARQUITETURA

A arquitetura deverá ser:

* segura;
* modular;
* escalável;
* auditável;
* observável;
* testável;
* resiliente;
* econômica;
* evolutiva;
* independente de um único ERP;
* preparada para múltiplas empresas e filiais;
* adequada à LGPD;
* preparada para grandes volumes de dados.

Não confunda escalabilidade com microserviços.

Compare, de maneira objetiva:

* monólito modular;
* microsserviços;
* arquitetura orientada a eventos;
* serverless;
* arquitetura híbrida.

Escolha a arquitetura mais apropriada para cada estágio do produto e explique:

* por que foi escolhida;
* alternativas consideradas;
* vantagens;
* limitações;
* custos;
* riscos;
* momento adequado para evolução.

Toda decisão estrutural relevante deverá gerar um ADR.

## 6. ARQUITETURA TÉCNICA

Projete e implemente:

### Frontend

* aplicação B2B responsiva;
* Next.js e React, ou alternativa tecnicamente superior;
* TypeScript em modo estrito;
* design system;
* componentes reutilizáveis;
* acessibilidade;
* internacionalização preparada;
* interface inicial em português do Brasil;
* gerenciamento seguro de sessão;
* tratamento global de erros;
* estados de carregamento;
* skeletons;
* empty states;
* tabelas com grandes volumes;
* filtros;
* paginação;
* exportação;
* gráficos;
* drill-down;
* feature flags;
* testes unitários;
* testes de componentes;
* testes end-to-end.

### Backend

* Python;
* FastAPI, ou alternativa justificada;
* arquitetura modular;
* separação entre domínio, aplicação e infraestrutura;
* APIs REST;
* OpenAPI;
* versionamento;
* validação;
* idempotência;
* rate limiting;
* filas;
* jobs assíncronos;
* webhooks;
* cache;
* logs estruturados;
* tracing;
* métricas;
* testes automatizados.

### Dados

Separar corretamente:

* banco transacional;
* camada analítica;
* armazenamento de arquivos;
* cache;
* filas;
* dados históricos;
* dados agregados;
* dados de Machine Learning;
* auditoria.

Avaliar e justificar o uso de:

* PostgreSQL;
* Redis;
* S3;
* DuckDB;
* ClickHouse;
* BigQuery;
* Redshift;
* TimescaleDB;
* mecanismos de busca;
* data lake;
* data warehouse.

Não adicionar tecnologias desnecessárias apenas para tornar a arquitetura aparentemente sofisticada.

## 7. STACK TECNOLÓGICA

Analise, compare, escolha e justifique todos os componentes.

Considere, sem obrigação de utilizar todos:

* Python;
* FastAPI;
* PostgreSQL;
* SQLAlchemy;
* Alembic;
* Pydantic;
* Redis;
* Celery;
* Dramatiq;
* RabbitMQ;
* Kafka;
* Pandas;
* Polars;
* DuckDB;
* Scikit-learn;
* XGBoost;
* LightGBM;
* Statsmodels;
* MLflow;
* React;
* Next.js;
* TypeScript;
* Docker;
* Kubernetes;
* Terraform;
* AWS;
* Cloudflare;
* S3;
* ECS;
* EKS;
* RDS;
* Supabase;
* Stripe;
* Asaas;
* GitHub Actions;
* OpenTelemetry;
* Prometheus;
* Grafana;
* Sentry.

Para cada escolha, documente:

* finalidade;
* justificativa;
* alternativas;
* limitações;
* impacto operacional;
* impacto financeiro;
* estratégia de evolução.

## 8. MULTI-TENANT

A plataforma deverá suportar:

* grupos econômicos;
* empresas;
* redes de farmácias;
* filiais;
* usuários;
* equipes;
* contadores;
* consultores;
* administradores;
* parceiros.

Projete isolamento rigoroso por tenant.

Defina:

* estratégia de tenant;
* chaves de isolamento;
* políticas de acesso;
* Row-Level Security, quando aplicável;
* prevenção de vazamento entre tenants;
* RBAC;
* permissões granulares;
* papéis personalizados;
* auditoria;
* impersonation administrativa controlada;
* limites por plano;
* quotas;
* billing por empresa, filial ou volume.

Crie testes automatizados específicos para impedir acesso cruzado entre tenants.

## 9. MODELAGEM DE DADOS

Crie a modelagem completa, incluindo:

* tenants;
* empresas;
* filiais;
* usuários;
* papéis;
* permissões;
* planos;
* assinaturas;
* cobranças;
* produtos;
* categorias;
* laboratórios;
* marcas;
* fornecedores;
* clientes;
* vendedores;
* vendas;
* itens de venda;
* compras;
* itens de compra;
* estoque;
* movimentações;
* lotes;
* validade;
* preços;
* custos;
* descontos;
* promoções;
* contas a pagar;
* contas a receber;
* fluxo de caixa;
* DRE;
* metas;
* campanhas;
* integrações;
* sincronizações;
* erros de importação;
* regras;
* alertas;
* diagnósticos;
* evidências;
* recomendações;
* planos de ação;
* tarefas;
* comentários;
* previsões;
* modelos;
* execuções de modelos;
* simulações;
* auditoria;
* eventos;
* logs funcionais.

Para cada tabela, apresentar:

* finalidade;
* colunas;
* tipos;
* constraints;
* relacionamentos;
* índices;
* chave de tenant;
* estratégia de retenção;
* estratégia de particionamento;
* estimativa de volume;
* cuidados de performance.

Crie migrations executáveis.

Planeje consultas para dezenas ou centenas de milhões de registros.

## 10. INTEGRAÇÃO COM ERPs

Implemente uma camada independente de fornecedores, baseada em connectors e adapters.

Suportar diferentes formas de integração:

* API REST;
* SOAP;
* webhook;
* banco de dados;
* SFTP;
* CSV;
* Excel;
* arquivos compactados;
* importação manual;
* agente local instalado no cliente.

Cada conector deverá contemplar:

* autenticação;
* mapeamento;
* sincronização inicial;
* sincronização incremental;
* cursor;
* paginação;
* retries;
* backoff exponencial;
* circuit breaker;
* idempotência;
* deduplicação;
* reconciliação;
* dead-letter queue;
* logs;
* métricas;
* alertas;
* reprocessamento;
* histórico de execução;
* validação de contrato;
* proteção de credenciais.

Criar um SDK interno para novos conectores.

Documentar como homologar um novo ERP.

## 11. PIPELINE DE DADOS

Projetar e implementar:

* ingestão;
* staging;
* validação;
* limpeza;
* padronização;
* enriquecimento;
* normalização;
* deduplicação;
* cálculo;
* agregação;
* publicação;
* reconciliação;
* monitoramento de qualidade.

Criar validações para:

* campos obrigatórios;
* valores negativos;
* datas inválidas;
* registros duplicados;
* produtos sem cadastro;
* estoque inconsistente;
* vendas canceladas;
* divergência de totais;
* custos ausentes;
* fornecedores não identificados;
* filiais incorretas.

Implementar catálogo de dados, linhagem, versionamento de transformações e score de qualidade por tenant.

## 12. KPIs FARMACÊUTICOS

Criar um catálogo com pelo menos 120 KPIs reais e acionáveis.

Separar por:

* compras;
* estoque;
* vendas;
* financeiro;
* fluxo de caixa;
* DRE;
* rentabilidade;
* precificação;
* CRM;
* marketing;
* operação;
* fornecedores;
* equipe;
* categorias;
* produtos;
* filiais;
* capital de giro.

Para cada KPI, informar:

* nome;
* objetivo;
* fórmula;
* unidade;
* granularidade;
* periodicidade;
* tabelas de origem;
* requisitos mínimos;
* faixas de referência configuráveis;
* interpretação;
* riscos;
* possíveis causas;
* ações recomendadas;
* limitações;
* exemplo prático.

As fórmulas devem ser armazenadas de forma versionada e testável.

## 13. MOTOR DE DIAGNÓSTICO

Não apresentar apenas indicadores.

O sistema deverá responder:

1. O que aconteceu?
2. Quando começou?
3. Qual a dimensão do problema?
4. Onde aconteceu?
5. Quais produtos, categorias ou filiais foram afetados?
6. Por que provavelmente aconteceu?
7. Que evidências sustentam a hipótese?
8. Qual o nível de confiança?
9. Que ação deve ser tomada?
10. Quem deve executar?
11. Qual o prazo recomendado?
12. Qual o impacto financeiro estimado?
13. Como confirmar se a ação funcionou?

O diagnóstico deverá combinar:

* regras determinísticas;
* análise estatística;
* comparação histórica;
* comparação entre filiais;
* detecção de anomalias;
* causalidade limitada e devidamente sinalizada;
* Machine Learning;
* explicação gerada por LLM apenas com dados verificados.

Cada diagnóstico deverá apresentar evidências rastreáveis.

Nenhuma recomendação poderá ser baseada apenas em texto gerado por IA.

## 14. MOTOR DE REGRAS

Criar um mecanismo de regras configurável e versionado.

As regras deverão possuir:

* identificador;
* categoria;
* descrição;
* severidade;
* condição;
* janela temporal;
* evidências;
* recomendação;
* impacto esperado;
* prioridade;
* versão;
* tenant;
* data de ativação;
* data de expiração;
* histórico de alterações.

Criar regras para, entre outros:

* estoque parado;
* ruptura;
* excesso de estoque;
* baixa cobertura;
* alta cobertura;
* margem negativa;
* queda de margem;
* custo crescente;
* desconto excessivo;
* compra acima da demanda;
* compra abaixo da demanda;
* capital parado;
* vencimento;
* baixo giro;
* alto giro;
* concentração em fornecedores;
* divergência de preço;
* produto de combate;
* produto sazonal;
* produto de prescrição;
* produto de indicação;
* elasticidade;
* GMROI;
* curva ABC;
* curva XYZ;
* churn;
* cross-sell;
* up-sell;
* queda de ticket;
* queda de conversão;
* perda de clientes;
* anomalias financeiras.

Implementar testes para cada grupo de regras.

## 15. INTELIGÊNCIA ARTIFICIAL E LLM

Explique e implemente controles claros sobre onde usar e onde não usar LLM.

LLM poderá ser utilizada para:

* traduzir análises técnicas para linguagem executiva;
* gerar resumos;
* explicar indicadores;
* organizar planos de ação;
* responder perguntas em linguagem natural;
* criar consultas analíticas controladas;
* resumir diagnósticos já calculados;
* apoiar navegação pela plataforma.

LLM não deverá:

* calcular indicadores financeiros críticos;
* acessar dados de outro tenant;
* inventar números;
* criar causas sem evidências;
* executar alterações destrutivas sem confirmação;
* decidir autonomamente sobre compras;
* substituir regras de segurança;
* acessar credenciais;
* gerar SQL irrestrito em produção.

Implementar:

* contexto controlado;
* RAG;
* tool calling;
* validação de entrada e saída;
* proteção contra prompt injection;
* mascaramento de dados;
* limites de custo;
* auditoria;
* versionamento de prompts;
* fallback;
* avaliação de respostas;
* citações internas das fontes utilizadas;
* confirmação humana para ações críticas.

## 16. MACHINE LEARNING

Projetar pipelines para:

* previsão de demanda;
* risco de ruptura;
* estoque ideal;
* compra sugerida;
* previsão de vendas;
* clusterização de clientes;
* clusterização de produtos;
* elasticidade de preço;
* análise de cesta;
* churn;
* propensão de compra;
* cross-sell;
* up-sell;
* anomalias;
* ticket médio;
* sazonalidade;
* previsão financeira.

Para cada modelo, documentar:

* problema;
* variável-alvo;
* features;
* fontes;
* janela de treinamento;
* prevenção de leakage;
* algoritmo-base;
* baseline;
* validação;
* métricas;
* explicabilidade;
* monitoramento;
* drift;
* retreinamento;
* rollback;
* aprovação;
* limites de uso.

Não utilize Machine Learning quando uma regra simples for mais segura, explicável e eficiente.

## 17. SIMULADORES

Implementar simuladores de:

* preço;
* desconto;
* promoção;
* compras;
* estoque;
* ruptura;
* fluxo de caixa;
* DRE;
* capital de giro;
* margem;
* mix de produtos;
* ROI;
* contratação;
* abertura de filial;
* cenários otimista, base e pessimista.

Cada simulação deverá registrar:

* premissas;
* dados utilizados;
* versão;
* autor;
* data;
* resultados;
* comparação;
* sensibilidade;
* limitações;
* histórico.

## 18. DASHBOARDS E EXPERIÊNCIA DO USUÁRIO

Projetar e implementar telas para:

* login;
* recuperação de senha;
* onboarding;
* seleção de empresa;
* seleção de filial;
* visão executiva;
* vendas;
* compras;
* estoque;
* financeiro;
* DRE;
* rentabilidade;
* clientes;
* fornecedores;
* campanhas;
* diagnósticos;
* alertas;
* recomendações;
* planos de ação;
* simuladores;
* integrações;
* qualidade dos dados;
* usuários;
* permissões;
* assinatura;
* configurações;
* auditoria;
* administração da plataforma.

Cada dashboard deverá ter:

* filtros;
* comparação temporal;
* comparação entre filiais;
* metas;
* tendências;
* alertas;
* explicações;
* drill-down;
* exportação;
* estados vazios;
* tratamento de erro;
* responsividade;
* performance adequada.

## 19. APIs

Definir e implementar:

* contratos;
* endpoints;
* schemas;
* autenticação;
* autorização;
* paginação;
* filtros;
* ordenação;
* versionamento;
* idempotência;
* rate limit;
* webhooks;
* erros padronizados;
* correlation ID;
* documentação OpenAPI;
* exemplos de requisição;
* exemplos de resposta.

Gerar coleção para testes de API.

## 20. SEGURANÇA E LGPD

Aplicar segurança desde a concepção.

Implementar:

* criptografia em trânsito;
* criptografia em repouso;
* gestão segura de segredos;
* RBAC;
* políticas por tenant;
* MFA preparado;
* sessões seguras;
* rotação de tokens;
* proteção contra ataques comuns;
* auditoria imutável;
* logs sem exposição de dados sensíveis;
* consentimento;
* retenção;
* anonimização;
* portabilidade;
* exclusão;
* resposta a incidentes;
* backups;
* restauração;
* plano de continuidade.

Usar como referências técnicas:

* OWASP;
* princípio do menor privilégio;
* defesa em profundidade;
* segurança por padrão;
* zero trust quando aplicável.

As exigências legais e regulatórias deverão ser validadas com profissionais jurídicos antes da operação comercial.

## 21. OBSERVABILIDADE E OPERAÇÃO

Implementar:

* logs estruturados;
* métricas;
* traces;
* dashboards operacionais;
* alertas;
* health checks;
* readiness checks;
* monitoramento de filas;
* monitoramento de integrações;
* monitoramento de jobs;
* monitoramento de modelos;
* monitoramento de custos.

Definir:

* SLIs;
* SLOs;
* SLAs;
* RPO;
* RTO;
* runbooks;
* escalonamento de incidentes;
* processo de post-mortem.

## 22. PERFORMANCE E ESCALABILIDADE

Projetar para milhares de empresas e milhões de registros.

Realizar:

* análise de consultas;
* índices;
* particionamento;
* cache;
* materialized views;
* agregações;
* processamento assíncrono;
* paginação;
* batch processing;
* controle de concorrência;
* testes de carga;
* testes de estresse;
* testes de soak.

Definir metas mensuráveis para:

* latência;
* throughput;
* tempo de carregamento;
* processamento de sincronização;
* geração de relatórios;
* disponibilidade.

## 23. INFRAESTRUTURA E DEPLOY

Entregar:

* Dockerfiles;
* Docker Compose para ambiente local;
* configurações por ambiente;
* infraestrutura como código;
* pipeline CI/CD;
* migrations automatizadas com controles;
* staging;
* produção;
* rollback;
* backup;
* restore;
* documentação de domínio;
* SSL;
* DNS;
* CDN;
* armazenamento;
* banco;
* filas;
* workers;
* monitoramento.

Comparar AWS, Supabase e outras alternativas antes da decisão.

Kubernetes deverá ser usado somente quando houver justificativa operacional e financeira real.

## 24. TESTES E QUALIDADE

Implementar:

* testes unitários;
* testes de integração;
* testes de contrato;
* testes de API;
* testes end-to-end;
* testes de segurança;
* testes de isolamento entre tenants;
* testes de carga;
* testes de migrations;
* testes de backup e restauração;
* testes dos cálculos de KPIs;
* testes das regras de diagnóstico;
* testes dos pipelines de dados;
* testes dos modelos.

Configurar:

* lint;
* formatter;
* type checking;
* análise de dependências;
* análise de vulnerabilidades;
* quality gates;
* cobertura mínima;
* execução automática no CI.

## 25. MONETIZAÇÃO

Implementar estrutura para:

* planos;
* períodos de teste;
* mensalidade;
* anualidade;
* cobrança por filial;
* cobrança por volume;
* limites;
* add-ons;
* upgrades;
* downgrades;
* cupons;
* inadimplência;
* cancelamento;
* reativação;
* enterprise;
* consultoria;
* marketplace;
* white-label.

Integrar o billing por abstração, permitindo Asaas, Stripe ou outro provedor.

## 26. BACKLOG E ROADMAP

Criar backlog completo dividido em:

* épicos;
* capabilities;
* features;
* histórias;
* tarefas;
* critérios de aceitação;
* prioridade;
* dependências;
* riscos;
* estimativa;
* responsável técnico sugerido.

Apresentar roadmap para:

* primeiros 30 dias;
* 90 dias;
* 6 meses;
* 1 ano;
* 2 anos;
* 5 anos.

O roadmap não deverá substituir a implementação.

## 27. DOCUMENTAÇÃO OBRIGATÓRIA

Entregar documentação para:

* instalação local;
* configuração;
* variáveis de ambiente;
* arquitetura;
* banco de dados;
* APIs;
* conectores;
* deploy;
* operação;
* segurança;
* backup;
* restauração;
* troubleshooting;
* criação de novos KPIs;
* criação de regras;
* criação de novos conectores;
* treinamento de modelos;
* uso do painel;
* administração do SaaS.

## 28. DEFINITION OF DONE

Uma funcionalidade somente poderá ser considerada concluída quando possuir:

1. código implementado;
2. validação de entrada;
3. tratamento de erros;
4. autorização;
5. isolamento de tenant;
6. logs;
7. métricas relevantes;
8. testes;
9. documentação;
10. migration, quando necessária;
11. interface, quando necessária;
12. critérios de aceitação atendidos;
13. revisão de segurança;
14. instrução de execução;
15. ausência de secrets no código.

## 29. FORMATO DE ENTREGA DE CADA ETAPA

Em cada etapa, apresente:

### Objetivo da etapa

Explique o que será construído.

### Decisões técnicas

Explique escolhas, alternativas e justificativas.

### Arquivos criados ou modificados

Liste os caminhos reais dos arquivos.

### Implementação

Implemente os arquivos necessários.

### Banco de dados

Inclua schemas e migrations.

### Testes

Implemente e informe como executar.

### Validação

Execute, sempre que o ambiente permitir:

* testes;
* lint;
* type check;
* build;
* migrations;
* verificações de segurança.

### Pendências reais

Liste somente dependências que exigem:

* credenciais;
* documentação externa;
* decisão comercial;
* validação jurídica;
* validação humana.

### Próxima etapa

Defina a sequência técnica mais lógica.

## 30. PRIMEIRA TAREFA

Comece realizando:

1. inspeção completa do repositório;
2. levantamento do estado atual;
3. identificação de riscos;
4. proposta de arquitetura;
5. criação da estrutura inicial;
6. configuração do ambiente local;
7. definição dos padrões de código;
8. criação dos documentos de arquitetura;
9. configuração de testes e CI;
10. implementação do primeiro módulo vertical completo.

O primeiro módulo vertical deverá contemplar:

* autenticação;
* tenant;
* empresa;
* filial;
* usuários;
* permissões;
* banco;
* backend;
* frontend;
* testes;
* auditoria;
* documentação.

Não pare apenas na análise. Após apresentar as decisões, inicie a implementação no repositório.
