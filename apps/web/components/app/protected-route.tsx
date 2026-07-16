"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { LoadingState } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const auth = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (auth.status === "anonymous") {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [auth.status, pathname, router]);

  if (auth.status === "loading") return <LoadingState label="Validando sessão segura" />;
  if (auth.status === "error") {
    return (
      <div className="state-card" role="alert">
        Não foi possível validar a sessão.
      </div>
    );
  }
  if (auth.status !== "authenticated" || !auth.me) return null;
  return <>{children}</>;
}
