const DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1";
export const DEFAULT_API_TIMEOUT_MS = 10_000;
const MAX_API_TIMEOUT_MS = 120_000;

function parsePublicUrl(value: string | undefined, fallback: string): string {
  const candidate = value?.trim() || fallback;
  try {
    return new URL(candidate).toString().replace(/\/$/, "");
  } catch {
    throw new Error("NEXT_PUBLIC_API_BASE_URL must be a valid absolute URL");
  }
}

function parsePublicTimeout(value: string | undefined): number {
  const candidate = value?.trim();
  if (!candidate) return DEFAULT_API_TIMEOUT_MS;
  if (!/^\d+$/.test(candidate)) {
    throw new Error("NEXT_PUBLIC_API_TIMEOUT_MS must be an integer in milliseconds");
  }

  const timeout = Number(candidate);
  if (!Number.isSafeInteger(timeout) || timeout < 100 || timeout > MAX_API_TIMEOUT_MS) {
    throw new Error("NEXT_PUBLIC_API_TIMEOUT_MS must be between 100 and 120000 milliseconds");
  }
  return timeout;
}

export const publicEnv = Object.freeze({
  apiBaseUrl: parsePublicUrl(process.env.NEXT_PUBLIC_API_BASE_URL, DEFAULT_API_BASE_URL),
  apiTimeoutMs: parsePublicTimeout(process.env.NEXT_PUBLIC_API_TIMEOUT_MS),
});
