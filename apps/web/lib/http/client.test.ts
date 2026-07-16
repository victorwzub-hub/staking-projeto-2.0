import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_API_TIMEOUT_MS } from "@/lib/env/public";

import { apiRequest, HttpError } from "./client";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("apiRequest", () => {
  it("returns a response received within the configured deadline", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(apiRequest<{ status: string }>("health", {}, fetcher)).resolves.toEqual({
      status: "ok",
    });
  });

  it("aborts a request that exceeds the configured timeout", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn<typeof fetch>().mockImplementation((_input, init) => {
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      });
    });

    const request = apiRequest("health", {}, fetcher);
    const rejection = expect(request).rejects.toMatchObject({
      code: "request_timeout",
      status: 0,
      message: "A solicitação excedeu o tempo limite. Tente novamente.",
    });

    await vi.advanceTimersByTimeAsync(DEFAULT_API_TIMEOUT_MS);
    await rejection;
  });

  it("returns an identifiable and safe network error", async () => {
    const fetcher = vi.fn<typeof fetch>().mockRejectedValue(new Error("socket details"));

    await expect(apiRequest("health", {}, fetcher)).rejects.toMatchObject({
      code: "network_error",
      status: 0,
      message: "Não foi possível conectar à API. Verifique sua conexão e tente novamente.",
    });
  });

  it("returns a comprehensible HTTP 401 error", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 401 }));

    await expect(apiRequest("me", {}, fetcher)).rejects.toMatchObject({
      code: "request_failed",
      status: 401,
      message: "Sua sessão expirou ou não é válida. Entre novamente.",
    });
  });

  it("returns a comprehensible HTTP 500 error", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 500 }));

    await expect(apiRequest("health", {}, fetcher)).rejects.toMatchObject({
      code: "request_failed",
      status: 500,
      message: "O serviço encontrou um erro inesperado. Tente novamente.",
    });
  });

  it("preserves an existing correlation id in the request and response error", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation((_input, init) => {
      const headers = new Headers(init?.headers);
      expect(headers.get("X-Correlation-ID")).toBe("web-correlation-123");
      return Promise.resolve(new Response(null, { status: 500 }));
    });

    await expect(
      apiRequest("health", { headers: { "X-Correlation-ID": "web-correlation-123" } }, fetcher),
    ).rejects.toEqual(
      new HttpError(
        "O serviço encontrou um erro inesperado. Tente novamente.",
        500,
        "web-correlation-123",
      ),
    );
  });

  it("preserves and respects an external abort signal", async () => {
    const external = new AbortController();
    const fetcher = vi.fn<typeof fetch>().mockImplementation((_input, init) => {
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      });
    });

    const request = apiRequest("health", { signal: external.signal }, fetcher);
    external.abort();

    await expect(request).rejects.toMatchObject({
      code: "request_aborted",
      status: 0,
      message: "A solicitação foi cancelada.",
    });
  });

  it("preserves the server correlation id on HTTP errors", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ error: true }), {
        status: 503,
        headers: { "X-Correlation-ID": "api-correlation" },
      }),
    );

    await expect(apiRequest("readiness", {}, fetcher)).rejects.toEqual(
      new HttpError(
        "O serviço encontrou um erro inesperado. Tente novamente.",
        503,
        "api-correlation",
      ),
    );
  });
});
