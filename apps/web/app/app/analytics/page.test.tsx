import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AnalyticsPage from "./page";

const apiRequest = vi.fn();
const apiJson = vi.fn();

vi.mock("@/lib/http/client", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
  apiJson: (...args: unknown[]) => apiJson(...args),
}));

vi.mock("@/lib/env/public", () => ({
  publicEnv: { apiBaseUrl: "http://api.test/api/v1" },
}));

vi.mock("@/lib/auth/auth-context", () => ({
  useAuth: () => ({
    hasPermission: () => true,
    me: { user: { id: "00000000-0000-0000-0000-000000000001" } },
  }),
}));

vi.mock("@/lib/http/use-api", () => ({
  useApi: (path: string) => {
    if (path === "analytics/filters") {
      return {
        status: "success",
        data: {
          economic_groups: [],
          companies: [{ id: "company-1", label: "Rede Central" }],
          branches: [{ id: "branch-1", label: "Matriz" }],
          products: [],
          categories: [],
          brands: [],
          suppliers: [],
          channels: ["store"],
          minimum_date: "2026-07-01",
          maximum_date: "2026-07-31",
        },
        error: null,
        reload: vi.fn(),
      };
    }
    if (path === "analytics/freshness") {
      return {
        status: "success",
        data: {
          data_version: 7,
          watermark: "2026-07-18T12:00:00Z",
          freshness_at: "2026-07-18T12:01:00Z",
          lag_seconds: 30,
          quality_score: "99.5",
          last_refresh_job_id: "job-1",
        },
        error: null,
        reload: vi.fn(),
      };
    }
    return { status: "success", data: [], error: null, reload: vi.fn() };
  },
}));

const NAMES: Record<string, string> = {
  "sales.net_revenue": "Receita líquida",
  "sales.average_ticket": "Ticket médio",
  "margin.gross_percent": "Margem bruta percentual",
  "inventory.value_cost": "Capital em estoque",
  "inventory.coverage_days": "Cobertura em dias",
  "operations.completeness": "Completude",
};

function result(code: string) {
  return {
    code,
    name: NAMES[code] ?? code,
    category: code.split(".")[0],
    unit: code.includes("percent") || code.includes("rate") ? "percent" : "BRL",
    value: "1234.5",
    reason: null,
    formula_version: 1,
    period_start: "2026-07-01",
    period_end: "2026-07-31",
    comparison_value: "1100",
    absolute_variation: "134.5",
    percentage_variation: "12.23",
    target_value: "1200",
    target_status: "met",
    freshness_at: "2026-07-18T12:01:00Z",
    quality_score: "99.5",
    data_version: 7,
    cache_status: "hit",
  };
}

describe("analytics dashboard", () => {
  beforeEach(() => {
    localStorage.clear();
    apiRequest.mockReset();
    apiJson.mockReset();
    apiRequest.mockImplementation((path: string) => {
      const cleanPath = path.split("?").at(0) ?? path;
      if (path.startsWith("analytics/comparisons/")) {
        return Promise.resolve({
          ...result(cleanPath.replace("analytics/comparisons/", "")),
          same_period_last_year_value: "1000",
          moving_average_28d_value: "1050",
          authorized_network_value: null,
          category_value: null,
        });
      }
      if (path.startsWith("analytics/results?")) {
        return Promise.resolve(
          [
            "sales.net_revenue",
            "sales.average_ticket",
            "margin.gross_percent",
            "inventory.value_cost",
            "inventory.coverage_days",
            "operations.completeness",
          ].map(result),
        );
      }
      if (path.startsWith("analytics/results/")) {
        return Promise.resolve(result(cleanPath.replace("analytics/results/", "")));
      }
      if (path.startsWith("analytics/timeseries/")) {
        return Promise.resolve([
          { period: "2026-07-01", value: "100", comparison_value: null, target_value: null },
          { period: "2026-07-02", value: "120", comparison_value: null, target_value: null },
        ]);
      }
      if (path.startsWith("analytics/rankings/")) {
        return Promise.resolve([
          {
            dimension_key: "product-1",
            label: "Dipirona",
            value: "300",
            share_percent: "24.3",
            rank: 1,
          },
        ]);
      }
      if (path.startsWith("analytics/drilldown/")) {
        return Promise.resolve([
          {
            fact_id: "fact-1",
            fact_type: "sale",
            occurred_at: "2026-07-18T10:00:00Z",
            company_id: "company-1",
            branch_id: "branch-1",
            product_id: null,
            supplier_id: null,
            canonical_table: "canonical_sales",
            canonical_record_id: "sale-1",
            canonical_version: "1",
            measures: { net_revenue: 300 },
            source_batch_id: "batch-1",
            transformation_version: "2c.1",
          },
        ]);
      }
      return Promise.resolve([]);
    });
    apiJson.mockResolvedValue({ id: "goal-1" });
  });

  it("loads real API indicators, comparison, trend, ranking and lineage", async () => {
    render(<AnalyticsPage />);

    expect(screen.getByRole("heading", { name: "Analytics farmacêutico" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("Receita líquida").length).toBeGreaterThan(0));
    expect(screen.getAllByText(/R\$\s*1\.234,50/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/12\.2% vs\. período anterior/).length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByText(/Dipirona/)).toBeInTheDocument());
    expect(screen.getByText("canonical_sales")).toBeInTheDocument();
    expect(screen.getByText("Fórmula v1")).toBeInTheDocument();
  });

  it("persists filters and creates an authorized goal", async () => {
    render(<AnalyticsPage />);
    await waitFor(() => expect(screen.getAllByText("Receita líquida").length).toBeGreaterThan(0));

    fireEvent.change(screen.getByLabelText("Empresa"), { target: { value: "company-1" } });
    fireEvent.change(screen.getByLabelText("Filial"), { target: { value: "branch-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Aplicar" }));
    expect(localStorage.getItem("pharma.analytics.filters")).toContain("company-1");

    fireEvent.change(screen.getByLabelText("Valor-alvo"), { target: { value: "1500" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar meta" }));
    await waitFor(() => expect(apiJson).toHaveBeenCalled());
    expect(apiJson.mock.calls.at(0)?.[0]).toBe("analytics/goals");
  });
});
