import { describe, expect, it, vi } from "vitest";
import { apiRequest, HttpError } from "./client";

describe("apiRequest", () => {
  it("returns parsed JSON for successful responses", async () => {
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

  it("throws a typed error and preserves the server correlation id", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ error: true }), {
        status: 503,
        headers: { "X-Correlation-ID": "api-correlation" },
      }),
    );

    await expect(apiRequest("readiness", {}, fetcher)).rejects.toEqual(
      new HttpError("API request failed with status 503", 503, "api-correlation"),
    );
  });
});
