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

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  fetcher: typeof fetch = fetch,
): Promise<T> {
  const correlationId = globalThis.crypto?.randomUUID?.() ?? `web-${Date.now()}`;
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Correlation-ID", correlationId);

  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (UNSAFE_METHODS.has(method) && !headers.has("X-CSRF-Token")) {
    const csrf = readCookie("pharma_csrf");
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }

  const response = await fetcher(`${publicEnv.apiBaseUrl}/${path.replace(/^\//, "")}`, {
    ...init,
    method,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    const body = await parseError(response);
    throw new HttpError(
      body?.error.message ?? `API request failed with status ${response.status}`,
      response.status,
      response.headers.get("X-Correlation-ID"),
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
