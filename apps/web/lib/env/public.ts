const DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1";

function parsePublicUrl(value: string | undefined, fallback: string): string {
  const candidate = value?.trim() || fallback;
  try {
    return new URL(candidate).toString().replace(/\/$/, "");
  } catch {
    throw new Error("NEXT_PUBLIC_API_BASE_URL must be a valid absolute URL");
  }
}

export const publicEnv = Object.freeze({
  apiBaseUrl: parsePublicUrl(process.env.NEXT_PUBLIC_API_BASE_URL, DEFAULT_API_BASE_URL),
});
