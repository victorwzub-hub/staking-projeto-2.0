import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiRequest } from "@/lib/http/client";

import { ApiStatus } from "./api-status";

vi.mock("@/lib/http/client", () => ({
  apiRequest: vi.fn(),
}));

const mockedApiRequest = vi.mocked(apiRequest);

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

describe("ApiStatus", () => {
  beforeEach(() => {
    mockedApiRequest.mockReset();
  });

  it("shows a loading state while the health request is pending", () => {
    const healthRequest = deferred<never>();
    mockedApiRequest.mockReturnValue(healthRequest.promise);

    render(<ApiStatus />);

    expect(screen.getByText("Verificando conexão com a API")).toBeInTheDocument();
    expect(screen.getByText(/Aguardando uma resposta real/)).toBeInTheDocument();
  });

  it("shows service metadata only after a successful health response", async () => {
    mockedApiRequest.mockResolvedValue({
      status: "ok",
      service: "Pharma Intelligence SaaS",
      version: "0.1.1",
    });

    render(<ApiStatus />);

    expect(await screen.findByText("API disponível")).toBeInTheDocument();
    expect(screen.getByText("Pharma Intelligence SaaS")).toBeInTheDocument();
    expect(screen.getByText("0.1.1")).toBeInTheDocument();
    expect(mockedApiRequest).toHaveBeenCalledWith("health", { cache: "no-store" });
  });

  it("shows an unavailable state and retries the real request", async () => {
    mockedApiRequest
      .mockRejectedValueOnce(new Error("A solicitação excedeu o tempo limite. Tente novamente."))
      .mockResolvedValueOnce({
        status: "ok",
        service: "Pharma Intelligence SaaS",
        version: "0.1.1",
      });

    render(<ApiStatus />);

    expect(await screen.findByRole("heading", { name: "API indisponível" })).toBeInTheDocument();
    expect(
      screen.getByText("A solicitação excedeu o tempo limite. Tente novamente."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByText("API disponível")).toBeInTheDocument();
    expect(mockedApiRequest).toHaveBeenCalledTimes(2);
  });
});
