"use client";

import type {
  ConnectorType,
  CursorPage,
  DataSource,
  ImportBatch,
  IntegrationObservability,
  MappingProfile,
  Page,
  ProcessingError,
  QualityResult,
} from "@pharma/contracts";
import { FormEvent, useMemo, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { FormField, SelectField } from "@/components/ui/form-field";
import { EmptyState, LoadingState, PageHeader } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson, apiRequest } from "@/lib/http/client";
import { useApi } from "@/lib/http/use-api";

const TERMINAL = new Set([
  "completed",
  "completed_with_warnings",
  "failed",
  "cancelled",
  "quarantined",
]);

const TARGET_FIELDS: Record<string, string[]> = {
  product: ["sku", "name", "ean", "brand", "manufacturer", "category", "unit", "presentation"],
  supplier: ["supplier_code", "name", "tax_id_hash", "lead_time_days", "minimum_order"],
  sale: ["sale_number", "occurred_at", "channel", "net_total", "items", "payments"],
  purchase: ["purchase_number", "supplier_code", "occurred_at", "status", "items"],
  stock: ["product_code", "occurred_at", "on_hand", "reserved", "in_transit"],
  price: ["product_code", "price", "reference_price", "reference_cost", "valid_from"],
};

function idempotencyKey(prefix: string) {
  return `${prefix}-${globalThis.crypto?.randomUUID?.() ?? Date.now()}`;
}

export default function IntegrationsPage() {
  const auth = useAuth();
  const connectors = useApi<ConnectorType[]>("integrations/connectors");
  const sources = useApi<Page<DataSource>>("integrations/sources?limit=100&offset=0");
  const batches = useApi<Page<ImportBatch>>("integrations/batches?limit=50&offset=0");
  const mappings = useApi<MappingProfile[]>("integrations/mappings");
  const observability = useApi<IntegrationObservability>(
    "integrations/observability",
    auth.hasPermission("integration.quality"),
  );
  const submit = useSubmit<unknown>();
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);
  const [uploadSourceId, setUploadSourceId] = useState("");
  const [canonicalDomain, setCanonicalDomain] = useState("products");
  const [canonicalCursor, setCanonicalCursor] = useState<string | null>(null);
  const [mappingEntity, setMappingEntity] = useState("product");
  const selectedBatch = batches.data?.items.find((item) => item.id === selectedBatchId) ?? null;
  const errors = useApi<ProcessingError[]>(
    selectedBatchId ? `integrations/batches/${selectedBatchId}/errors` : "",
    Boolean(selectedBatchId && auth.hasPermission("integration.errors")),
  );
  const quality = useApi<QualityResult[]>(
    selectedBatchId ? `integrations/batches/${selectedBatchId}/quality` : "",
    Boolean(selectedBatchId && auth.hasPermission("integration.quality")),
  );
  const context = auth.me?.contexts.find(
    (item) => item.tenant_id === auth.me?.active_session.active_tenant_id,
  );
  const companies = context?.companies ?? [];
  const fileSources = useMemo(
    () => sources.data?.items.filter((source) => source.connector_key === "file-upload") ?? [],
    [sources.data],
  );
  const canonical = useApi<CursorPage<Record<string, unknown>>>(
    `integrations/canonical/${canonicalDomain}?limit=25${
      canonicalCursor ? `&cursor=${encodeURIComponent(canonicalCursor)}` : ""
    }`,
  );

  async function reload() {
    await Promise.all([
      sources.reload(),
      batches.reload(),
      mappings.reload(),
      observability.reload(),
      canonical.reload(),
    ]);
  }

  async function createSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const element = event.currentTarget;
    const form = new FormData(element);
    const companyId = String(form.get("company_id") ?? "");
    const company = companies.find((item) => item.id === companyId);
    const connectorKey = String(form.get("connector_key"));
    const result = await submit.run(() =>
      apiJson<DataSource>("integrations/sources", "POST", {
        name: form.get("name"),
        connector_key: connectorKey,
        connector_version: "1.0.0",
        company_id: companyId,
        branch_id: String(form.get("branch_id") ?? "") || company?.branches[0]?.id || null,
        credential_reference_id: null,
        dataset_type: form.get("dataset_type"),
        sync_mode: "incremental",
        schedule_cron: null,
        configuration:
          connectorKey === "deterministic-erp"
            ? { records: Number(form.get("records") ?? 5), seed: "pharma-web" }
            : {},
      }),
    );
    if (result) {
      element.reset();
      await reload();
    }
  }

  async function testSource(source: DataSource) {
    await submit.run(() => apiJson(`integrations/sources/${source.id}/test`, "POST"));
    await sources.reload();
  }

  async function syncSource(source: DataSource) {
    await submit.run(() =>
      apiRequest(`integrations/sources/${source.id}/sync`, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey("sync") },
        body: JSON.stringify({ mode: "incremental", entities: [] }),
      }),
    );
    await batches.reload();
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const element = event.currentTarget;
    const form = new FormData(element);
    const result = await submit.run(() =>
      apiRequest(`integrations/sources/${uploadSourceId}/upload`, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey("upload") },
        body: form,
      }),
    );
    if (result) {
      element.reset();
      setUploadSourceId("");
      await batches.reload();
    }
  }

  async function createMapping(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const element = event.currentTarget;
    const form = new FormData(element);
    const result = await submit.run(() =>
      apiJson("integrations/mappings", "POST", {
        name: form.get("mapping_name"),
        data_source_id: form.get("mapping_source_id"),
        dataset_type: mappingEntity,
        connector_version: "1.0.0",
        source_schema_version: "2026-07",
        publish: form.get("publish") === "on",
        fields: [
          {
            source_field: form.get("source_field"),
            target_entity: mappingEntity,
            target_field: form.get("target_field"),
            transform_type: form.get("transform_type"),
            transform_config: {},
            required: form.get("required") === "on",
            default_value: null,
          },
        ],
      }),
    );
    if (result) {
      element.reset();
      setMappingEntity("product");
      await mappings.reload();
    }
  }

  async function cancel(batch: ImportBatch) {
    await submit.run(() => apiJson(`integrations/batches/${batch.id}/cancel`, "POST"));
    await batches.reload();
  }

  async function reprocess(batch: ImportBatch) {
    await submit.run(() =>
      apiRequest(`integrations/batches/${batch.id}/reprocess`, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey("reprocess") },
      }),
    );
    await batches.reload();
  }

  return (
    <>
      <PageHeader
        eyebrow="Plataforma de dados canônica"
        title="Integrações ERP"
        description="Configure fontes, importe arquivos e acompanhe qualidade, erros e progresso."
        action={
          <button className="button button-secondary" onClick={reload}>
            Atualizar
          </button>
        }
      />
      {submit.error ? <Alert title="Operação não concluída">{submit.error.message}</Alert> : null}

      <section className="metric-grid" aria-label="Resumo das integrações">
        <div className="metric-card">
          <span>Conectores</span>
          <strong>{connectors.data?.length ?? "—"}</strong>
        </div>
        <div className="metric-card">
          <span>Fontes ativas</span>
          <strong>
            {sources.data?.items.filter((item) => item.status === "active").length ?? "—"}
          </strong>
        </div>
        <div className="metric-card">
          <span>Backlog</span>
          <strong>{observability.data?.backlog ?? "—"}</strong>
        </div>
        <div className="metric-card">
          <span>Qualidade média</span>
          <strong>{observability.data?.average_quality_score?.toFixed(2) ?? "—"}%</strong>
        </div>
      </section>

      {auth.hasPermission("integration.create") ? (
        <form className="content-card form-grid" onSubmit={createSource}>
          <h2 className="form-span">Nova fonte de dados</h2>
          <FormField label="Nome" name="name" required maxLength={160} />
          <SelectField label="Conector" name="connector_key" required>
            <option value="deterministic-erp">ERP determinístico</option>
            <option value="file-upload">Importação de arquivo</option>
          </SelectField>
          <SelectField label="Empresa" name="company_id" required>
            <option value="">Selecione</option>
            {companies.map((company) => (
              <option key={company.id} value={company.id}>
                {company.name}
              </option>
            ))}
          </SelectField>
          <SelectField label="Filial" name="branch_id">
            <option value="">Filial padrão</option>
            {companies.flatMap((company) =>
              company.branches.map((branch) => (
                <option key={branch.id} value={branch.id}>
                  {company.name} · {branch.name}
                </option>
              )),
            )}
          </SelectField>
          <SelectField label="Domínio" name="dataset_type" defaultValue="all">
            <option value="all">Todos</option>
            <option value="product">Produtos</option>
            <option value="supplier">Fornecedores</option>
            <option value="sale">Vendas</option>
            <option value="purchase">Compras</option>
            <option value="stock">Estoque</option>
            <option value="price">Preços</option>
          </SelectField>
          <FormField
            label="Registros por domínio"
            name="records"
            type="number"
            min={1}
            max={10000}
            defaultValue={5}
          />
          <div className="form-span">
            <button className="button" disabled={submit.pending || companies.length === 0}>
              Criar fonte
            </button>
          </div>
        </form>
      ) : null}

      {auth.hasPermission("integration.sync") && fileSources.length ? (
        <form className="content-card form-grid" onSubmit={upload}>
          <h2 className="form-span">Importar arquivo</h2>
          <SelectField
            label="Fonte"
            name="source_id"
            value={uploadSourceId}
            onChange={(event) => setUploadSourceId(event.target.value)}
            required
          >
            <option value="">Selecione</option>
            {fileSources.map((source) => (
              <option key={source.id} value={source.id}>
                {source.name}
              </option>
            ))}
          </SelectField>
          <SelectField label="Domínio" name="dataset_type" defaultValue="product">
            <option value="product">Produtos</option>
            <option value="supplier">Fornecedores</option>
            <option value="sale">Vendas</option>
            <option value="purchase">Compras</option>
            <option value="stock">Estoque</option>
            <option value="price">Preços</option>
            <option value="all">Todos (NDJSON)</option>
          </SelectField>
          <FormField
            label="Arquivo"
            name="file"
            type="file"
            accept=".csv,.json,.jsonl,.ndjson"
            required
          />
          <div className="form-span">
            <button className="button" disabled={submit.pending || !uploadSourceId}>
              Enviar e processar
            </button>
          </div>
        </form>
      ) : null}

      {auth.hasPermission("integration.mapping") && sources.data?.items.length ? (
        <form className="content-card form-grid" onSubmit={createMapping}>
          <h2 className="form-span">Mapeamento versionado</h2>
          <FormField label="Nome do perfil" name="mapping_name" required maxLength={160} />
          <SelectField label="Fonte" name="mapping_source_id" required>
            <option value="">Selecione</option>
            {sources.data.items.map((source) => (
              <option key={source.id} value={source.id}>
                {source.name}
              </option>
            ))}
          </SelectField>
          <SelectField
            label="Entidade"
            name="mapping_entity"
            value={mappingEntity}
            onChange={(event) => setMappingEntity(event.target.value)}
          >
            {Object.keys(TARGET_FIELDS).map((entity) => (
              <option key={entity} value={entity}>
                {entity}
              </option>
            ))}
          </SelectField>
          <FormField label="Campo de origem" name="source_field" required maxLength={200} />
          <SelectField label="Campo canônico" name="target_field" required>
            {(TARGET_FIELDS[mappingEntity] ?? []).map((field) => (
              <option key={field} value={field}>
                {field}
              </option>
            ))}
          </SelectField>
          <SelectField label="Transformação" name="transform_type" defaultValue="identity">
            <option value="identity">Sem transformação</option>
            <option value="trim">Remover espaços</option>
            <option value="uppercase">Maiúsculas</option>
            <option value="lowercase">Minúsculas</option>
            <option value="decimal">Decimal</option>
            <option value="integer">Inteiro</option>
            <option value="date">Data</option>
            <option value="datetime">Data e hora</option>
            <option value="boolean">Booleano</option>
          </SelectField>
          <label className="check-field">
            <input type="checkbox" name="required" /> Campo obrigatório
          </label>
          <label className="check-field">
            <input type="checkbox" name="publish" /> Validar e publicar versão
          </label>
          <div className="form-span">
            <button className="button" disabled={submit.pending}>
              Salvar mapeamento
            </button>
          </div>
          {mappings.data?.length ? (
            <p className="form-span">
              {mappings.data.length} versão(ões) de mapeamento cadastrada(s).
            </p>
          ) : null}
        </form>
      ) : null}

      <section className="content-card">
        <h2>Fontes configuradas</h2>
        {sources.status === "loading" ? (
          <LoadingState />
        ) : sources.status === "error" ? (
          <Alert title="Fontes indisponíveis">{sources.error.message}</Alert>
        ) : sources.data.items.length === 0 ? (
          <EmptyState title="Nenhuma fonte" description="Crie uma fonte ERP ou de arquivo." />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Fonte</th>
                  <th>Conector</th>
                  <th>Domínio</th>
                  <th>Saúde</th>
                  <th>Último sync</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {sources.data.items.map((source) => (
                  <tr key={source.id}>
                    <td>
                      <strong>{source.name}</strong>
                      <br />
                      <small>{source.status}</small>
                    </td>
                    <td>{source.connector_key}</td>
                    <td>{source.dataset_type}</td>
                    <td>
                      <span
                        className={`badge ${source.last_health_status === "healthy" ? "badge-success" : ""}`}
                      >
                        {source.last_health_status ?? "não testada"}
                      </span>
                    </td>
                    <td>
                      {source.last_sync_at
                        ? new Date(source.last_sync_at).toLocaleString("pt-BR")
                        : "—"}
                    </td>
                    <td>
                      <div className="table-actions">
                        {auth.hasPermission("integration.test") ? (
                          <button className="link-button" onClick={() => testSource(source)}>
                            Testar
                          </button>
                        ) : null}
                        {auth.hasPermission("integration.sync") &&
                        source.connector_key !== "file-upload" ? (
                          <button className="link-button" onClick={() => syncSource(source)}>
                            Sincronizar
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="content-card">
        <h2>Lotes de processamento</h2>
        {batches.status === "loading" ? (
          <LoadingState />
        ) : batches.status === "error" ? (
          <Alert title="Lotes indisponíveis">{batches.error.message}</Alert>
        ) : batches.data.items.length === 0 ? (
          <EmptyState title="Nenhum lote" description="Sincronize uma fonte ou envie um arquivo." />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Criado</th>
                  <th>Domínio</th>
                  <th>Estado</th>
                  <th>Progresso</th>
                  <th>Registros</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {batches.data.items.map((batch) => (
                  <tr key={batch.id} className={selectedBatchId === batch.id ? "selected-row" : ""}>
                    <td>{new Date(batch.created_at).toLocaleString("pt-BR")}</td>
                    <td>{batch.dataset_type}</td>
                    <td>
                      <span className={`badge batch-state-${batch.state}`}>
                        {batch.state.replaceAll("_", " ")}
                      </span>
                    </td>
                    <td>
                      <div className="progress-track" aria-label={`${batch.progress_percent}%`}>
                        <span style={{ width: `${batch.progress_percent}%` }} />
                      </div>
                    </td>
                    <td>
                      {batch.valid_records}/{batch.received_records} válidos
                      {batch.rejected_records ? ` · ${batch.rejected_records} rejeitados` : ""}
                    </td>
                    <td>
                      <div className="table-actions">
                        <button
                          className="link-button"
                          onClick={() => setSelectedBatchId(batch.id)}
                        >
                          Detalhes
                        </button>
                        {auth.hasPermission("integration.cancel") && !TERMINAL.has(batch.state) ? (
                          <button className="link-button danger" onClick={() => cancel(batch)}>
                            Cancelar
                          </button>
                        ) : null}
                        {auth.hasPermission("integration.reprocess") &&
                        TERMINAL.has(batch.state) ? (
                          <button className="link-button" onClick={() => reprocess(batch)}>
                            Reprocessar
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="content-card">
        <div className="detail-heading">
          <div>
            <p className="eyebrow">Modelo canônico</p>
            <h2>Dados normalizados</h2>
          </div>
          <SelectField
            label="Domínio"
            name="canonical_domain"
            value={canonicalDomain}
            onChange={(event) => {
              setCanonicalDomain(event.target.value);
              setCanonicalCursor(null);
            }}
          >
            <option value="products">Produtos</option>
            <option value="suppliers">Fornecedores</option>
            <option value="sales">Vendas</option>
            <option value="purchases">Compras</option>
            <option value="inventory">Estoque</option>
            <option value="prices">Preços</option>
          </SelectField>
        </div>
        {canonical.status === "loading" ? (
          <LoadingState label="Carregando dados canônicos" />
        ) : canonical.status === "error" ? (
          <Alert title="Dados indisponíveis">{canonical.error.message}</Alert>
        ) : canonical.data.items.length === 0 ? (
          <EmptyState
            title="Nenhum registro"
            description="Este domínio ainda não recebeu dados válidos."
          />
        ) : (
          <>
            <div className="canonical-grid">
              {canonical.data.items.map((item) => (
                <article className="canonical-record" key={String(item.id)}>
                  {Object.entries(item).map(([key, value]) => (
                    <div key={key}>
                      <span>{key.replaceAll("_", " ")}</span>
                      <strong>{value === null ? "—" : String(value)}</strong>
                    </div>
                  ))}
                </article>
              ))}
            </div>
            <div className="pagination">
              <button
                className="button button-secondary"
                disabled={!canonicalCursor}
                onClick={() => setCanonicalCursor(null)}
              >
                Primeira página
              </button>
              <button
                className="button button-secondary"
                disabled={!canonical.data.next_cursor}
                onClick={() => setCanonicalCursor(canonical.data.next_cursor)}
              >
                Próxima página
              </button>
            </div>
          </>
        )}
      </section>

      {selectedBatch ? (
        <section className="content-card integration-detail">
          <div className="detail-heading">
            <div>
              <p className="eyebrow">Lote selecionado</p>
              <h2>{selectedBatch.id}</h2>
            </div>
            <button className="button button-quiet" onClick={() => setSelectedBatchId(null)}>
              Fechar
            </button>
          </div>
          <div className="metric-grid compact-metrics">
            <div className="metric-card">
              <span>Recebidos</span>
              <strong>{selectedBatch.received_records}</strong>
            </div>
            <div className="metric-card">
              <span>Válidos</span>
              <strong>{selectedBatch.valid_records}</strong>
            </div>
            <div className="metric-card">
              <span>Rejeitados</span>
              <strong>{selectedBatch.rejected_records}</strong>
            </div>
            <div className="metric-card">
              <span>Duplicados</span>
              <strong>{selectedBatch.duplicate_records}</strong>
            </div>
          </div>
          {auth.hasPermission("integration.quality") ? (
            <div>
              <h3>Qualidade</h3>
              {quality.status === "loading" ? (
                <LoadingState />
              ) : quality.status === "error" ? (
                <Alert title="Qualidade indisponível">{quality.error.message}</Alert>
              ) : quality.data.length === 0 ? (
                <p>Nenhuma ocorrência.</p>
              ) : (
                <ul className="quality-list">
                  {quality.data.map((item) => (
                    <li key={item.id}>
                      <strong>{item.rule_key}</strong>
                      <span>
                        {item.entity_type} · {item.failed_records}/{item.evaluated_records} falhas ·{" "}
                        {item.score.toFixed(2)}%
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}
          {auth.hasPermission("integration.errors") ? (
            <div>
              <h3>Erros e avisos</h3>
              {errors.status === "loading" ? (
                <LoadingState />
              ) : errors.status === "error" ? (
                <Alert title="Erros indisponíveis">{errors.error.message}</Alert>
              ) : errors.data.length === 0 ? (
                <p>Nenhum erro registrado.</p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Etapa</th>
                        <th>Severidade</th>
                        <th>Código</th>
                        <th>Mensagem</th>
                      </tr>
                    </thead>
                    <tbody>
                      {errors.data.map((item) => (
                        <tr key={item.id}>
                          <td>{item.step_name}</td>
                          <td>{item.severity}</td>
                          <td>
                            <code>{item.error_code}</code>
                          </td>
                          <td>{item.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : null}
        </section>
      ) : null}
    </>
  );
}
