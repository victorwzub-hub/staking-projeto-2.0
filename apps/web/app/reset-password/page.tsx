"use client";

import type { MessageResponse } from "@pharma/contracts";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent } from "react";

import { AuthMessage } from "@/components/auth/auth-message";
import { AuthShell } from "@/components/auth/auth-shell";
import { FormField } from "@/components/ui/form-field";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";

export default function ResetPasswordPage() {
  const token = useSearchParams().get("token");
  const submit = useSubmit<MessageResponse>();
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await submit.run(() =>
      apiJson("auth/reset-password", "POST", { token, new_password: form.get("password") }),
    );
  }
  return (
    <AuthShell
      title="Definir nova senha"
      description="O token será consumido uma única vez e todas as sessões anteriores serão revogadas."
    >
      {!token ? (
        <AuthMessage error={new Error("Token de redefinição ausente.")} />
      ) : (
        <form className="form-stack" onSubmit={handleSubmit}>
          <AuthMessage
            error={submit.error}
            success={submit.data ? "Senha redefinida. Entre novamente." : null}
          />
          <FormField
            label="Nova senha"
            name="password"
            type="password"
            minLength={12}
            autoComplete="new-password"
            required
          />
          <button className="button" disabled={submit.pending}>
            {submit.pending ? "Atualizando…" : "Redefinir senha"}
          </button>
        </form>
      )}
      <div className="auth-links">
        <Link href="/login">Ir para login</Link>
      </div>
    </AuthShell>
  );
}
