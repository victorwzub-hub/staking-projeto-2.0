"use client";

import type { MessageResponse } from "@pharma/contracts";
import Link from "next/link";
import { FormEvent } from "react";

import { AuthMessage } from "@/components/auth/auth-message";
import { AuthShell } from "@/components/auth/auth-shell";
import { FormField } from "@/components/ui/form-field";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";

export default function ResendVerificationPage() {
  const submit = useSubmit<MessageResponse>();
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await submit.run(() =>
      apiJson("auth/resend-verification", "POST", { email: form.get("email") }),
    );
  }
  return (
    <AuthShell
      title="Reenviar verificação"
      description="A resposta é neutra para proteger a existência das contas."
    >
      <form className="form-stack" onSubmit={handleSubmit}>
        <AuthMessage
          error={submit.error}
          success={submit.data ? "Se a conta existir, um novo link será preparado." : null}
        />
        <FormField label="E-mail" name="email" type="email" required />
        <button className="button" disabled={submit.pending}>
          {submit.pending ? "Enviando…" : "Solicitar link"}
        </button>
      </form>
      <div className="auth-links">
        <Link href="/login">Voltar ao login</Link>
      </div>
    </AuthShell>
  );
}
