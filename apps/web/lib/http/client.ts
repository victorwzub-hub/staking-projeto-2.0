import type { ApiErrorResponse } from "@pharma/contracts";

import { publicEnv } from "@/lib/env/public";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class HttpError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly correlationId: string | null,
    public readonly code: string = "request_failed",
    public readonly details: unknown = {},
  ) {
    super(message);
    this.name = "HttpError";
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${encodeURIComponent(name)}=`;
  for (const part of document.cookie.split(";")) {
    const value = part.trim();
    if (value.startsWith(prefix)) return decodeURIComponent(value.slice(prefix.length));
  }
  return null;
}

async function parseError(response: Response): Promise<ApiErrorResponse | null> {
  try {
    return (await response.json()) as ApiErrorResponse;
  } catch {
    return null;
  }
}

function defaultHttpErrorMessage(status: number): string {
  if (status === 401) return "Sua sessão expirou ou não é válida. Entre novamente.";
  if (status >= 500) return "O serviço encontrou um erro inesperado. Tente novamente.";
  return `A API recusou a solicitação com status ${status}.`;
}

function createRequestController(externalSignal: AbortSignal | null | undefined) {
  const controller = new AbortController();
  const abortFromExternal = () => controller.abort(externalSignal?.reason);

  if (externalSignal?.aborted) {
    abortFromExternal();
  } else {
    externalSignal?.addEventListener("abort", abortFromExternal, { once: true });
  }

  return {
    controller,
    detach: () => externalSignal?.removeEventListener("abort", abortFromExternal),
  };
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  fetcher: typeof fetch = fetch,
): Promise<T> {
  const headers = new Headers(init.headers);
  const correlationId =
    headers.get("X-Correlation-ID")?.trim() ||
    globalThis.crypto?.randomUUID?.() ||
    `web-${Date.now()}`;
  const method = (init.method ?? "GET").toUpperCase();
  headers.set("Accept", "application/json");
  headers.set("X-Correlation-ID", correlationId);

  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (UNSAFE_METHODS.has(method) && !headers.has("X-CSRF-Token")) {
    const csrf = readCookie("pharma_csrf");
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }

  const { controller, detach } = createRequestController(init.signal);
  let timedOut = false;
  const timeoutId = globalThis.setTimeout(() => {
    timedOut = true;
    controller.abort(new DOMException("Request timed out", "TimeoutError"));
  }, publicEnv.apiTimeoutMs);

  let response: Response;
  try {
    response = await fetcher(`${publicEnv.apiBaseUrl}/${path.replace(/^\//, "")}`, {
      ...init,
      method,
      headers,
      credentials: "include",
      signal: controller.signal,
    });
  } catch {
    if (timedOut) {
      throw new HttpError(
        "A solicitação excedeu o tempo limite. Tente novamente.",
        0,
        correlationId,
        "request_timeout",
      );
    }
    if (controller.signal.aborted) {
      throw new HttpError("A solicitação foi cancelada.", 0, correlationId, "request_aborted");
    }
    throw new HttpError(
      "Não foi possível conectar à API. Verifique sua conexão e tente novamente.",
      0,
      correlationId,
      "network_error",
    );
  } finally {
    globalThis.clearTimeout(timeoutId);
    detach();
  }

  if (!response.ok) {
    const body = await parseError(response);
    throw new HttpError(
      body?.error.message ?? defaultHttpErrorMessage(response.status),
      response.status,
      response.headers.get("X-Correlation-ID") ?? correlationId,
      body?.error.code ?? "request_failed",
      body?.error.details ?? {},
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function apiJson<T>(path: string, method: string, body?: unknown): Promise<T> {
  return apiRequest<T>(path, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}
