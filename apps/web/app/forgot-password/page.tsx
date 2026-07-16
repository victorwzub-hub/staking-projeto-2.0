"use client";

import type { MessageResponse } from "@pharma/contracts";
import Link from "next/link";
import { FormEvent } from "react";

import { AuthMessage } from "@/components/auth/auth-message";
import { AuthShell } from "@/components/auth/auth-shell";
import { FormField } from "@/components/ui/form-field";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";

export default function ForgotPasswordPage() {
  const submit = useSubmit<MessageResponse>();
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await submit.run(() => apiJson("auth/forgot-password", "POST", { email: form.get("email") }));
  }
  return (
    <AuthShell
      title="Recuperar acesso"
      description="Solicite um token de uso único, com expiração e resposta contra enumeração."
    >
      <form className="form-stack" onSubmit={handleSubmit}>
        <AuthMessage
          error={submit.error}
          success={submit.data ? "Se a conta existir, as instruções serão preparadas." : null}
        />
        <FormField label="E-mail" name="email" type="email" required />
        <button className="button" disabled={submit.pending}>
          {submit.pending ? "Solicitando…" : "Recuperar senha"}
        </button>
      </form>
      <div className="auth-links">
        <Link href="/login">Voltar ao login</Link>
      </div>
    </AuthShell>
  );
}
