"use client";

import type { MessageResponse } from "@pharma/contracts";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect } from "react";

import { AuthMessage } from "@/components/auth/auth-message";
import { AuthShell } from "@/components/auth/auth-shell";
import { LoadingState } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";

export default function AcceptInvitationPage() {
  const token = useSearchParams().get("token");
  const auth = useAuth();
  const submit = useSubmit<MessageResponse>();

  useEffect(() => {
    if (token && auth.status === "authenticated" && !submit.data && !submit.error) {
      void submit.run(() => apiJson("invitations/accept", "POST", { token }));
    }
  }, [auth.status, submit, token]);

  const next = `/invitations/accept?token=${encodeURIComponent(token ?? "")}`;
  return (
    <AuthShell
      title="Aceitar convite"
      description="O convite é associado ao e-mail correto e só pode ser utilizado uma vez."
    >
      {!token ? <AuthMessage error={new Error("Token de convite ausente.")} /> : null}
      {token && auth.status === "loading" ? <LoadingState label="Validando sessão" /> : null}
      {token && auth.status === "anonymous" ? (
        <>
          <AuthMessage success="Entre com o e-mail convidado. Se ainda não tiver conta, crie e verifique uma identidade antes de retornar a este link." />
          <div className="auth-links">
            <Link className="button" href={`/login?next=${encodeURIComponent(next)}`}>
              Entrar
            </Link>
            <Link className="button button-secondary" href="/register">
              Criar conta
            </Link>
          </div>
        </>
      ) : null}
      {token && auth.status === "authenticated" && submit.pending ? (
        <LoadingState label="Validando convite" />
      ) : null}
      {token && auth.status === "authenticated" && !submit.pending ? (
        <AuthMessage
          error={submit.error}
          success={submit.data ? "Convite aceito. O novo tenant já pode ser selecionado." : null}
        />
      ) : null}
      {submit.data ? (
        <div className="auth-links">
          <Link href="/app/select-context">Selecionar tenant</Link>
        </div>
      ) : null}
    </AuthShell>
  );
}
