"use client";

import type { MessageResponse } from "@pharma/contracts";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect } from "react";

import { AuthMessage } from "@/components/auth/auth-message";
import { AuthShell } from "@/components/auth/auth-shell";
import { LoadingState } from "@/components/ui/page-state";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";

export default function VerifyEmailPage() {
  const search = useSearchParams();
  const token = search.get("token");
  const submit = useSubmit<MessageResponse>();
  useEffect(() => {
    if (token && !submit.data && !submit.error)
      void submit.run(() => apiJson("auth/verify-email", "POST", { token }));
  }, [token, submit]);
  return (
    <AuthShell
      title="Verificação de e-mail"
      description="A confirmação protege sua identidade antes do primeiro acesso."
    >
      {!token ? (
        <AuthMessage error={new Error("Token de verificação ausente.")} />
      ) : submit.pending ? (
        <LoadingState label="Verificando e-mail" />
      ) : (
        <AuthMessage
          error={submit.error}
          success={submit.data ? "E-mail confirmado. Sua conta já pode entrar." : null}
        />
      )}
      <div className="auth-links">
        <Link href="/login">Ir para login</Link>
        <Link href="/resend-verification">Solicitar novo link</Link>
      </div>
    </AuthShell>
  );
}
