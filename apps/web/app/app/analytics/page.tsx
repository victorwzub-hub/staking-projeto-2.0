"use client";

import type {
  AnalyticsAvailableFilters,
  AnalyticsDrillDownItem,
  AnalyticsFreshness,
  AnalyticsGoal,
  AnalyticsKpiComparison,
  AnalyticsKpiResult,
  AnalyticsRankingItem,
  AnalyticsTimePoint,
} from "@pharma/contracts";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { EmptyState, LoadingState, PageHeader } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson, apiRequest } from "@/lib/http/client";
import { publicEnv } from "@/lib/env/public";
import { useApi } from "@/lib/http/use-api";

type DashboardSection = "executive" | "sales" | "inventory" | "purchases" | "margin" | "quality";
type QueryFilters = {
  from: string;
  to: string;
  economicGroupId: string;
  companyId: string;
  branchId: string;
  productId: string;
  categoryId: string;
  brandId: string;
  supplierId: string;
  channel: string;
};

const SECTIONS: Record<DashboardSection, { label: string; codes: string[] }> = {
  executive: {
    label: "Visão executiva",
    codes: [
      "sales.net_revenue",
      "sales.average_ticket",
      "margin.gross_percent",
      "inventory.value_cost",
      "inventory.coverage_days",
      "operations.completeness",
    ],
  },
  sales: {
    label: "Vendas",
    codes: [
      "sales.gross_revenue",
      "sales.net_revenue",
      "sales.units_sold",
      "sales.average_ticket",
      "sales.items_per_sale",
      "sales.return_rate",
    ],
  },
  inventory: {
    label: "Estoque",
    codes: [
      "inventory.value_cost",
      "inventory.available",
      "inventory.coverage_days",
      "inventory.turnover",
      "inventory.zero_stock_rate",
      "inventory.excess_count",
    ],
  },
  purchases: {
    label: "Compras e fornecedores",
    codes: [
      "purchases.net_value",
      "purchases.quantity",
      "purchases.average_unit_cost",
      "suppliers.average_lead_time",
      "suppliers.on_time_rate",
      "suppliers.top5_concentration",
    ],
  },
  margin: {
    label: "Margem e rentabilidade",
    codes: [
      "margin.gross_profit",
      "margin.gross_percent",
      "margin.cogs",
      "margin.gmroi",
      "margin.markdown",
      "margin.negative_margin_rate",
    ],
  },
  quality: {
    label: "Qualidade e atualização",
    codes: [
      "operations.data_freshness",
      "operations.source_lag",
      "operations.completeness",
      "operations.rejection_rate",
      "operations.duplicate_rate",
      "operations.integration_availability",
    ],
  },
};

const DEFAULT_KPI = "sales.net_revenue";

function isoDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function initialFilters(): QueryFilters {
  const now = new Date();
  return {
    from: isoDate(new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1))),
    to: isoDate(now),
    economicGroupId: "",
    companyId: "",
    branchId: "",
    productId: "",
    categoryId: "",
    brandId: "",
    supplierId: "",
    channel: "",
  };
}

function queryString(filters: QueryFilters) {
  const params = new URLSearchParams({ from: filters.from, to: filters.to });
  if (filters.economicGroupId) params.set("economic_group_id", filters.economicGroupId);
  if (filters.companyId) params.set("company_id", filters.companyId);
  if (filters.branchId) params.set("branch_id", filters.branchId);
  if (filters.productId) params.set("product_id", filters.productId);
  if (filters.categoryId) params.set("category_id", filters.categoryId);
  if (filters.brandId) params.set("brand_id", filters.brandId);
  if (filters.supplierId) params.set("supplier_id", filters.supplierId);
  if (filters.channel) params.set("channel", filters.channel);
  return params.toString();
}

function formatValue(value: string | null, unit: string) {
  if (value === null) return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  if (unit === "BRL") {
    return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(numeric);
  }
  if (unit === "percent")
    return `${numeric.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
  return `${numeric.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}${unit === "count" ? "" : ` ${unit}`}`;
}

function Sparkline({ points }: { points: AnalyticsTimePoint[] }) {
  const values = points.map((point) => Number(point.value)).filter(Number.isFinite);
  if (values.length < 2) return <div className="analytics-chart-empty">Série insuficiente</div>;
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = maximum - minimum || 1;
  const path = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * 100;
      const y = 38 - ((value - minimum) / range) * 34;
      return `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  return (
    <svg
      className="analytics-sparkline"
      viewBox="0 0 100 42"
      role="img"
      aria-label="Tendência do indicador"
    >
      <path
        d={path}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export default function AnalyticsPage() {
  const auth = useAuth();
  const [section, setSection] = useState<DashboardSection>("executive");
  const [filters, setFilters] = useState<QueryFilters>(initialFilters);
  const [applied, setApplied] = useState<QueryFilters>(initialFilters);
  const [results, setResults] = useState<AnalyticsKpiResult[]>([]);
  const [series, setSeries] = useState<AnalyticsTimePoint[]>([]);
  const [ranking, setRanking] = useState<AnalyticsRankingItem[]>([]);
  const [details, setDetails] = useState<AnalyticsDrillDownItem[]>([]);
  const [comparisons, setComparisons] = useState<AnalyticsKpiComparison | null>(null);
  const [selectedCode, setSelectedCode] = useState(DEFAULT_KPI);
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [error, setError] = useState<Error | null>(null);
  const available = useApi<AnalyticsAvailableFilters>("analytics/filters");
  const freshness = useApi<AnalyticsFreshness>("analytics/freshness");
  const goals = useApi<AnalyticsGoal[]>("analytics/goals");
  const submit = useSubmit<AnalyticsGoal>();
  const query = useMemo(() => queryString(applied), [applied]);
  const canViewFinancial = auth.hasPermission("analytics.financial");
  const sectionCodes = useMemo(
    () => SECTIONS[section].codes.filter((code) => !code.startsWith("margin.") || canViewFinancial),
    [canViewFinancial, section],
  );

  useEffect(() => {
    const timer = globalThis.setTimeout(() => {
      const stored = globalThis.localStorage?.getItem("pharma.analytics.filters");
      if (!stored) return;
      try {
        const parsed = { ...initialFilters(), ...(JSON.parse(stored) as Partial<QueryFilters>) };
        setFilters(parsed);
        setApplied(parsed);
      } catch {
        globalThis.localStorage?.removeItem("pharma.analytics.filters");
      }
    }, 0);
    return () => globalThis.clearTimeout(timer);
  }, []);

  const loadDashboard = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const codes = sectionCodes;
      const payload = await apiRequest<AnalyticsKpiResult[]>(
        `analytics/results?${query}&codes=${encodeURIComponent(codes.join(","))}`,
      );
      setResults(payload);
      const firstCode = codes.at(0);
      if (firstCode && !codes.includes(selectedCode)) setSelectedCode(firstCode);
      setStatus("success");
    } catch (reason) {
      setError(reason as Error);
      setStatus("error");
    }
  }, [query, sectionCodes, selectedCode]);

  useEffect(() => {
    const timer = globalThis.setTimeout(() => void loadDashboard(), 0);
    return () => globalThis.clearTimeout(timer);
  }, [loadDashboard]);

  useEffect(() => {
    let active = true;
    void Promise.all([
      apiRequest<AnalyticsKpiComparison>(`analytics/comparisons/${selectedCode}?${query}`),
      apiRequest<AnalyticsTimePoint[]>(`analytics/timeseries/${selectedCode}?${query}`),
      apiRequest<AnalyticsRankingItem[]>(
        `analytics/rankings/${selectedCode}?${query}&dimension=product&limit=10`,
      ),
      auth.hasPermission("analytics.detail")
        ? apiRequest<AnalyticsDrillDownItem[]>(
            `analytics/drilldown/${selectedCode}?${query}&limit=25&offset=0`,
          )
        : Promise.resolve([]),
    ])
      .then(([nextComparisons, nextSeries, nextRanking, nextDetails]) => {
        if (!active) return;
        setComparisons(nextComparisons);
        setSeries(nextSeries);
        setRanking(nextRanking);
        setDetails(nextDetails);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason as Error);
      });
    return () => {
      active = false;
    };
  }, [auth, query, selectedCode]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    globalThis.localStorage?.setItem("pharma.analytics.filters", JSON.stringify(filters));
    setApplied(filters);
  }

  async function addGoal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const activeUser = auth.me?.user.id;
    if (!activeUser) return;
    const result = await submit.run(() =>
      apiJson<AnalyticsGoal>("analytics/goals", "POST", {
        company_id: applied.companyId || null,
        branch_id: applied.branchId || null,
        kpi_code: selectedCode,
        period_start: applied.from,
        period_end: applied.to,
        target_value: form.get("target_value"),
        lower_value: null,
        upper_value: null,
        direction: "increase",
        owner_user_id: activeUser,
        note: form.get("note") || null,
      }),
    );
    if (result) {
      formElement.reset();
      await Promise.all([goals.reload(), loadDashboard()]);
    }
  }

  const exportUrl = `${publicEnv.apiBaseUrl}/analytics/export.csv?${query}&codes=${encodeURIComponent(
    sectionCodes.join(","),
  )}`;
  const selected = results.find((item) => item.code === selectedCode);

  return (
    <>
      <PageHeader
        eyebrow={`Warehouse analítico • versão dos dados ${freshness.data?.data_version ?? 0}`}
        title="Analytics farmacêutico"
        description="Indicadores rastreáveis, metas, comparação de períodos e drill-down com escopo autorizado."
        action={
          auth.hasPermission("analytics.export") ? (
            <a className="button button-secondary" href={exportUrl} download>
              Exportar CSV
            </a>
          ) : null
        }
      />

      <form className="analytics-filters" onSubmit={applyFilters} aria-label="Filtros globais">
        <label>
          De
          <input
            type="date"
            value={filters.from}
            onChange={(event) => setFilters({ ...filters, from: event.target.value })}
            required
          />
        </label>
        <label>
          Grupo econômico
          <select
            value={filters.economicGroupId}
            onChange={(event) =>
              setFilters({
                ...filters,
                economicGroupId: event.target.value,
                companyId: "",
                branchId: "",
              })
            }
          >
            <option value="">Todos autorizados</option>
            {available.data?.economic_groups.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Até
          <input
            type="date"
            value={filters.to}
            onChange={(event) => setFilters({ ...filters, to: event.target.value })}
            required
          />
        </label>
        <label>
          Produto
          <select
            value={filters.productId}
            onChange={(event) =>
              setFilters({
                ...filters,
                productId: event.target.value,
                categoryId: "",
                brandId: "",
                supplierId: "",
                channel: "",
              })
            }
          >
            <option value="">Todos</option>
            {available.data?.products.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Categoria
          <select
            value={filters.categoryId}
            onChange={(event) =>
              setFilters({
                ...filters,
                categoryId: event.target.value,
                productId: "",
                brandId: "",
                supplierId: "",
                channel: "",
              })
            }
          >
            <option value="">Todas</option>
            {available.data?.categories.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Marca
          <select
            value={filters.brandId}
            onChange={(event) =>
              setFilters({
                ...filters,
                brandId: event.target.value,
                productId: "",
                categoryId: "",
                supplierId: "",
                channel: "",
              })
            }
          >
            <option value="">Todas</option>
            {available.data?.brands.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Fornecedor
          <select
            value={filters.supplierId}
            onChange={(event) =>
              setFilters({
                ...filters,
                supplierId: event.target.value,
                productId: "",
                categoryId: "",
                brandId: "",
                channel: "",
              })
            }
          >
            <option value="">Todos</option>
            {available.data?.suppliers.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Empresa
          <select
            value={filters.companyId}
            onChange={(event) =>
              setFilters({ ...filters, companyId: event.target.value, branchId: "" })
            }
          >
            <option value="">Todas autorizadas</option>
            {available.data?.companies.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Filial
          <select
            value={filters.branchId}
            disabled={!filters.companyId}
            onChange={(event) => setFilters({ ...filters, branchId: event.target.value })}
          >
            <option value="">Todas autorizadas</option>
            {available.data?.branches.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Canal
          <select
            value={filters.channel}
            onChange={(event) =>
              setFilters({
                ...filters,
                channel: event.target.value,
                productId: "",
                categoryId: "",
                brandId: "",
                supplierId: "",
              })
            }
          >
            <option value="">Todos</option>
            {available.data?.channels.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <button className="button" type="submit">
          Aplicar
        </button>
      </form>

      <div className="analytics-freshness" role="status">
        <span>
          Atualizado:{" "}
          {freshness.data?.freshness_at
            ? new Date(freshness.data.freshness_at).toLocaleString("pt-BR")
            : "aguardando primeira carga"}
        </span>
        <span>
          Qualidade:{" "}
          {freshness.data?.quality_score
            ? `${Number(freshness.data.quality_score).toFixed(1)}%`
            : "—"}
        </span>
      </div>

      <div className="analytics-tabs" role="tablist" aria-label="Áreas analíticas">
        {(
          Object.entries(SECTIONS) as Array<[DashboardSection, (typeof SECTIONS)[DashboardSection]]>
        )
          .filter(([key]) => key !== "margin" || canViewFinancial)
          .map(([key, item]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={section === key}
              className={section === key ? "active" : ""}
              onClick={() => setSection(key)}
            >
              {item.label}
            </button>
          ))}
      </div>

      {error ? <Alert title="Não foi possível carregar analytics">{error.message}</Alert> : null}
      {status === "loading" ? <LoadingState label="Calculando indicadores autorizados" /> : null}
      {status === "error" ? (
        <button className="button" onClick={loadDashboard}>
          Tentar novamente
        </button>
      ) : null}
      {status === "success" && results.every((item) => item.reason === "no_data") ? (
        <EmptyState
          title="Sem dados no período"
          description="Importe dados pela plataforma de integrações ou altere os filtros."
        />
      ) : null}

      {status === "success" ? (
        <section className="analytics-kpi-grid" aria-label={SECTIONS[section].label}>
          {results.map((item) => (
            <button
              key={item.code}
              type="button"
              className={`analytics-kpi-card ${selectedCode === item.code ? "selected" : ""}`}
              onClick={() => setSelectedCode(item.code)}
            >
              <span>{item.name}</span>
              <strong>{formatValue(item.value, item.unit)}</strong>
              <small className={Number(item.percentage_variation) >= 0 ? "positive" : "negative"}>
                {item.percentage_variation === null
                  ? "Sem comparação"
                  : `${Number(item.percentage_variation) >= 0 ? "+" : ""}${Number(item.percentage_variation).toFixed(1)}% vs. período anterior`}
              </small>
              {item.target_value !== null ? (
                <small>
                  Meta {formatValue(item.target_value, item.unit)} •{" "}
                  {item.target_status === "met" ? "atingida" : "abaixo"}
                </small>
              ) : null}
            </button>
          ))}
        </section>
      ) : null}

      <section className="analytics-detail-grid">
        <article className="panel analytics-trend-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Tendência diária</p>
              <h2>{selected?.name ?? "Indicador"}</h2>
            </div>
            <span>{selected?.formula_version ? `Fórmula v${selected.formula_version}` : ""}</span>
          </div>
          <Sparkline points={series} />
          <div className="analytics-series-labels">
            <span>{series.at(0)?.period ?? "—"}</span>
            <span>{series.at(-1)?.period ?? "—"}</span>
          </div>
        </article>
        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Ranking</p>
              <h2>Produtos</h2>
            </div>
          </div>
          {ranking.length ? (
            <ol className="analytics-ranking">
              {ranking.map((item) => (
                <li key={item.dimension_key}>
                  <span>
                    {item.rank}. {item.label}
                  </span>
                  <strong>{formatValue(item.value, selected?.unit ?? "")}</strong>
                  <small>
                    {item.share_percent ? `${Number(item.share_percent).toFixed(1)}%` : "—"}
                  </small>
                </li>
              ))}
            </ol>
          ) : (
            <EmptyState
              title="Sem composição"
              description="Não há produtos para o indicador e período."
            />
          )}
        </article>
        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Comparações governadas</p>
              <h2>Referências do período</h2>
            </div>
          </div>
          <dl className="analytics-comparison-list">
            <div>
              <dt>Mesmo período do ano anterior</dt>
              <dd>
                {formatValue(
                  comparisons?.same_period_last_year_value ?? null,
                  selected?.unit ?? "",
                )}
              </dd>
            </div>
            <div>
              <dt>Média móvel de 28 dias</dt>
              <dd>
                {formatValue(comparisons?.moving_average_28d_value ?? null, selected?.unit ?? "")}
              </dd>
            </div>
            <div>
              <dt>Rede autorizada</dt>
              <dd>
                {formatValue(comparisons?.authorized_network_value ?? null, selected?.unit ?? "")}
              </dd>
            </div>
            <div>
              <dt>Categoria do produto</dt>
              <dd>{formatValue(comparisons?.category_value ?? null, selected?.unit ?? "")}</dd>
            </div>
          </dl>
        </article>
      </section>

      {auth.hasPermission("analytics.goals.manage") ? (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Governança</p>
              <h2>Meta para {selected?.name}</h2>
            </div>
          </div>
          {submit.error ? <Alert title="Meta não salva">{submit.error.message}</Alert> : null}
          <form className="inline-form" onSubmit={addGoal}>
            <label>
              Valor-alvo
              <input name="target_value" type="number" step="0.0001" required />
            </label>
            <label>
              Observação
              <input name="note" maxLength={2000} />
            </label>
            <button className="button" disabled={submit.pending}>
              {submit.pending ? "Salvando…" : "Salvar meta"}
            </button>
          </form>
        </section>
      ) : null}

      {auth.hasPermission("analytics.detail") ? (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Drill-down auditável</p>
              <h2>Registros de origem</h2>
            </div>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Tipo</th>
                  <th>Tabela canônica</th>
                  <th>Registro</th>
                  <th>Versão</th>
                  <th>Medidas</th>
                </tr>
              </thead>
              <tbody>
                {details.map((item) => (
                  <tr key={item.fact_id}>
                    <td>{new Date(item.occurred_at).toLocaleString("pt-BR")}</td>
                    <td>{item.fact_type}</td>
                    <td>{item.canonical_table}</td>
                    <td>
                      <code>{item.canonical_record_id}</code>
                    </td>
                    <td>
                      {item.canonical_version} / {item.transformation_version}
                    </td>
                    <td>
                      <code>{JSON.stringify(item.measures)}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!details.length ? (
            <EmptyState
              title="Sem registros"
              description="Nenhum fato originou esse indicador no período."
            />
          ) : null}
        </section>
      ) : (
        <Alert title="Detalhes protegidos">
          Seu papel permite indicadores agregados, mas não o drill-down.
        </Alert>
      )}
    </>
  );
}
