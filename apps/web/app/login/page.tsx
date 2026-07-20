"use client";

import type { LoginResponse } from "@pharma/contracts";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent } from "react";

import { AuthMessage } from "@/components/auth/auth-message";
import { AuthShell } from "@/components/auth/auth-shell";
import { FormField } from "@/components/ui/form-field";
import { useAuth } from "@/lib/auth/auth-context";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";

export default function LoginPage() {
  const submit = useSubmit<LoginResponse>();
  const auth = useAuth();
  const router = useRouter();
  const search = useSearchParams();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const result = await submit.run(() =>
      apiJson<LoginResponse>("auth/login", "POST", {
        email: form.get("email"),
        password: form.get("password"),
      }),
    );
    if (!result) return;
    await auth.refresh();
    const next = search.get("next");
    router.replace(
      result.onboarding_required ? "/onboarding" : next?.startsWith("/") ? next : "/app",
    );
  }

  return (
    <AuthShell
      title="Acesse sua conta"
      description="Sessão opaca protegida por cookie HttpOnly, sem credenciais permanentes no navegador."
    >
      <form className="form-stack" onSubmit={handleSubmit}>
        <AuthMessage error={submit.error} />
        <FormField label="E-mail" name="email" type="email" autoComplete="email" required />
        <FormField
          label="Senha"
          name="password"
          type="password"
          autoComplete="current-password"
          required
        />
        <button className="button" type="submit" disabled={submit.pending}>
          {submit.pending ? "Entrando…" : "Entrar"}
        </button>
      </form>
      <div className="auth-links">
        <Link href="/forgot-password">Esqueci minha senha</Link>
        <Link href="/register">Criar conta</Link>
      </div>
    </AuthShell>
  );
}
