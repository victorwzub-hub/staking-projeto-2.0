import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("public environment", () => {
  it("uses a validated public API timeout", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_TIMEOUT_MS", "2500");

    const { publicEnv } = await import("./public");

    expect(publicEnv.apiTimeoutMs).toBe(2500);
  });

  it("rejects an invalid public API timeout", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_TIMEOUT_MS", "not-a-number");

    await expect(import("./public")).rejects.toThrow(
      "NEXT_PUBLIC_API_TIMEOUT_MS must be an integer in milliseconds",
    );
  });
});
