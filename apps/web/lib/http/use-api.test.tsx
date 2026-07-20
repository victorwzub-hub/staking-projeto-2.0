import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useApi } from "./use-api";

const apiRequest = vi.fn();
vi.mock("@/lib/http/client", () => ({ apiRequest: (...args: unknown[]) => apiRequest(...args) }));

describe("useApi", () => {
  beforeEach(() => vi.clearAllMocks());
  it("moves from loading to success", async () => {
    apiRequest.mockResolvedValue({ value: 1 });
    const { result } = renderHook(() => useApi<{ value: number }>("resource"));
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.data).toEqual({ value: 1 });
  });
  it("exposes errors and supports retry", async () => {
    apiRequest.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ value: 2 });
    const { result } = renderHook(() => useApi<{ value: number }>("resource"));
    await waitFor(() => expect(result.current.status).toBe("error"));
    await act(async () => {
      await act(async () => {
        await result.current.reload();
      });
    });
    await waitFor(() => expect(result.current.status).toBe("success"));
  });
});
