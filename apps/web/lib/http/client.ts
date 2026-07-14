import { publicEnv } from "@/lib/env/public";

export class HttpError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly correlationId: string | null,
  ) {
    super(message);
    this.name = "HttpError";
  }
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  fetcher: typeof fetch = fetch,
): Promise<T> {
  const correlationId = globalThis.crypto?.randomUUID?.() ?? `web-${Date.now()}`;
  const response = await fetcher(`${publicEnv.apiBaseUrl}/${path.replace(/^\//, "")}`, {
    ...init,
    headers: {
      Accept: "application/json",
      "X-Correlation-ID": correlationId,
      ...init.headers,
    },
  });

  if (!response.ok) {
    throw new HttpError(
      `API request failed with status ${response.status}`,
      response.status,
      response.headers.get("X-Correlation-ID"),
    );
  }

  return (await response.json()) as T;
}
