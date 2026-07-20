import type { Company } from "@pharma/contracts";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "@/lib/auth/auth-context";
import { apiJson } from "@/lib/http/client";
import { useApi } from "@/lib/http/use-api";

import CompaniesPage from "./page";

vi.mock("@/lib/auth/auth-context", () => ({
  useAuth: vi.fn(),
}));
vi.mock("@/lib/http/client", () => ({
  apiJson: vi.fn(),
}));
vi.mock("@/lib/http/use-api", () => ({
  useApi: vi.fn(),
}));

const mockedUseAuth = vi.mocked(useAuth);
const mockedApiJson = vi.mocked(apiJson);
const mockedUseApi = vi.mocked(useApi);
const reload = vi.fn();

const createdCompany: Company = {
  id: "company-2",
  tenant_id: "tenant-1",
  economic_group_id: null,
  legal_name: "Segunda Empresa Ltda",
  trade_name: "Segunda Empresa",
  slug: "segunda-empresa",
  status: "active",
  version: 1,
};

describe("CompaniesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    reload.mockResolvedValue(undefined);
    mockedUseAuth.mockReturnValue({
      status: "authenticated",
      me: null,
      error: null,
      refresh: vi.fn().mockResolvedValue(null),
      hasPermission: () => true,
    });
    mockedUseApi.mockReturnValue({
      status: "success",
      data: [],
      error: null,
      reload,
    });
    mockedApiJson.mockResolvedValue(createdCompany);
  });

  it("resets the submitted form and reloads companies after the async request", async () => {
    render(<CompaniesPage />);

    const legalName = screen.getByLabelText("Razão social");
    const tradeName = screen.getByLabelText("Nome fantasia");
    const slug = screen.getByLabelText("Identificador");
    fireEvent.change(legalName, { target: { value: createdCompany.legal_name } });
    fireEvent.change(tradeName, { target: { value: createdCompany.trade_name } });
    fireEvent.change(slug, { target: { value: createdCompany.slug } });
    fireEvent.submit(screen.getByRole("button", { name: "Criar empresa" }).closest("form")!);

    await waitFor(() => expect(reload).toHaveBeenCalledOnce());
    expect(mockedApiJson).toHaveBeenCalledWith("companies", "POST", {
      legal_name: createdCompany.legal_name,
      trade_name: createdCompany.trade_name,
      slug: createdCompany.slug,
      economic_group_id: null,
    });
    expect(legalName).toHaveValue("");
    expect(tradeName).toHaveValue("");
    expect(slug).toHaveValue("");
  });
});
