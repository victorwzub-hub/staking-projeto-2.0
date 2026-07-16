"use client";

import type { MessageResponse } from "@pharma/contracts";
import Link from "next/link";
import { FormEvent } from "react";

import { AuthMessage } from "@/components/auth/auth-message";
import { AuthShell } from "@/components/auth/auth-shell";
import { FormField } from "@/components/ui/form-field";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";

export default function RegisterPage() {
  const submit = useSubmit<MessageResponse>();
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await submit.run(() =>
      apiJson<MessageResponse>("auth/register", "POST", {
        display_name: form.get("display_name"),
        email: form.get("email"),
        password: form.get("password"),
      }),
    );
  }
  return (
    <AuthShell
      title="Crie sua identidade"
      description="Uma identidade global pode participar de mais de uma organização com acessos independentes."
    >
      <form className="form-stack" onSubmit={handleSubmit}>
        <AuthMessage
          error={submit.error}
          success={submit.data ? "Confira seu e-mail para verificar a conta." : null}
        />
        <FormField label="Nome" name="display_name" autoComplete="name" minLength={2} required />
        <FormField
          label="E-mail profissional"
          name="email"
          type="email"
          autoComplete="email"
          required
        />
        <FormField
          label="Senha"
          name="password"
          type="password"
          autoComplete="new-password"
          minLength={12}
          hint="Use ao menos 12 caracteres."
          required
        />
        <button className="button" type="submit" disabled={submit.pending}>
          {submit.pending ? "Criando…" : "Criar conta"}
        </button>
      </form>
      <div className="auth-links">
        <Link href="/login">Já tenho uma conta</Link>
        <Link href="/resend-verification">Reenviar verificação</Link>
      </div>
    </AuthShell>
  );
}
