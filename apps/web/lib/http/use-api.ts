"use client";

import { useCallback, useEffect, useState } from "react";

import { apiRequest } from "@/lib/http/client";

export type ApiState<T> =
  | { status: "loading"; data: null; error: null }
  | { status: "success"; data: T; error: null }
  | { status: "error"; data: null; error: Error };

type KeyedState<T> = ApiState<T> & { key: string };

export function useApi<T>(path: string, enabled = true) {
  const [state, setState] = useState<KeyedState<T>>({
    key: path,
    status: "loading",
    data: null,
    error: null,
  });

  const load = useCallback(async () => {
    if (!enabled) return;
    setState({ key: path, status: "loading", data: null, error: null });
    try {
      const data = await apiRequest<T>(path, { cache: "no-store" });
      setState({ key: path, status: "success", data, error: null });
    } catch (error) {
      setState({ key: path, status: "error", data: null, error: error as Error });
    }
  }, [enabled, path]);

  useEffect(() => {
    if (!enabled) return;
    let active = true;
    void apiRequest<T>(path, { cache: "no-store" })
      .then((data) => {
        if (active) setState({ key: path, status: "success", data, error: null });
      })
      .catch((error: unknown) => {
        if (active) setState({ key: path, status: "error", data: null, error: error as Error });
      });
    return () => {
      active = false;
    };
  }, [enabled, path]);

  const visibleState: ApiState<T> =
    state.key === path ? state : { status: "loading", data: null, error: null };

  return { ...visibleState, reload: load };
}
