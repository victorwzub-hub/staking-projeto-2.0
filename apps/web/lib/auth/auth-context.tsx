"use client";

import type { MeResponse } from "@pharma/contracts";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { apiRequest, HttpError } from "@/lib/http/client";

type AuthStatus = "loading" | "authenticated" | "anonymous" | "error";

type AuthValue = {
  status: AuthStatus;
  me: MeResponse | null;
  error: Error | null;
  refresh: () => Promise<MeResponse | null>;
  hasPermission: (permission: string) => boolean;
};

const AuthContext = createContext<AuthValue | null>(null);

function classifyFailure(reason: unknown): { status: AuthStatus; error: Error | null } {
  if (reason instanceof HttpError && reason.status === 401) {
    return { status: "anonymous", error: null };
  }
  return { status: "error", error: reason as Error };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [me, setMe] = useState<MeResponse | null>(null);
  const [error, setError] = useState<Error | null>(null);

  const refresh = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const value = await apiRequest<MeResponse>("me", { cache: "no-store" });
      setMe(value);
      setStatus("authenticated");
      return value;
    } catch (reason) {
      const failure = classifyFailure(reason);
      setMe(null);
      setStatus(failure.status);
      setError(failure.error);
      return null;
    }
  }, []);

  useEffect(() => {
    let active = true;
    void apiRequest<MeResponse>("me", { cache: "no-store" })
      .then((value) => {
        if (!active) return;
        setMe(value);
        setStatus("authenticated");
      })
      .catch((reason: unknown) => {
        if (!active) return;
        const failure = classifyFailure(reason);
        setMe(null);
        setStatus(failure.status);
        setError(failure.error);
      });
    return () => {
      active = false;
    };
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      status,
      me,
      error,
      refresh,
      hasPermission: (permission) => Boolean(me?.permissions.includes(permission)),
    }),
    [status, me, error, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
