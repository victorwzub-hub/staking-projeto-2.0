"use client";

import type { OnboardingProgress, TermsVersion } from "@pharma/contracts";
import { useRouter } from "next/navigation";
import { FormEvent } from "react";

import { ProtectedRoute } from "@/components/app/protected-route";
import { Alert } from "@/components/ui/alert";
import { FormField, SelectField } from "@/components/ui/form-field";
import { LoadingState } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";
import { useApi } from "@/lib/http/use-api";

export default function OnboardingPage() {
  return (
    <ProtectedRoute>
      <OnboardingContent />
    </ProtectedRoute>
  );
}

function OnboardingContent() {
  const progress = useApi<OnboardingProgress>("onboarding");
  const terms = useApi<TermsVersion[]>("onboarding/terms");
  const submit = useSubmit<{
    tenant_id: string;
    company_id: string;
    branch_id: string;
    membership_id: string;
    status: string;
  }>();
  const auth = useAuth();
  const router = useRouter();

  if (progress.status === "loading" || terms.status === "loading")
    return (
      <div className="public-page">
        <LoadingState label="Carregando onboarding seguro" />
      </div>
    );
  if (progress.status === "error" || terms.status === "error")
    return (
      <div className="public-page">
        <Alert tone="danger" title="Onboarding indisponível">
          Não foi possível carregar os dados necessários.
        </Alert>
      </div>
    );
  if (progress.data.status === "completed")
    return (
      <div className="public-page narrow">
        <Alert tone="success" title="Onboarding concluído">
          Sua organização já está configurada.
        </Alert>
        <button className="button" onClick={() => router.replace("/app")}>
          Acessar aplicação
        </button>
      </div>
    );

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const result = await submit.run(() =>
      apiJson<{
        tenant_id: string;
        company_id: string;
        branch_id: string;
        membership_id: string;
        status: string;
      }>("onboarding/complete", "POST", {
        tenant_name: form.get("tenant_name"),
        tenant_slug: form.get("tenant_slug"),
        economic_group_name: form.get("economic_group_name") || null,
        company_legal_name: form.get("company_legal_name"),
        company_trade_name: form.get("company_trade_name"),
        company_slug: form.get("company_slug"),
        branch_name: form.get("branch_name"),
        branch_slug: form.get("branch_slug"),
        terms_version_id: form.get("terms_version_id"),
        accept_terms: form.get("accept_terms") === "on",
      }),
    );
    if (result) {
      await auth.refresh();
      router.replace("/app");
    }
  }

  return (
    <main className="public-page">
      <section className="onboarding-card">
        <p className="eyebrow">Configuração inicial retomável</p>
        <h1>Crie sua primeira organização</h1>
        <p>O fluxo é idempotente: reenvios não duplicam tenant, empresa, filial ou membership.</p>
        <form className="form-grid" onSubmit={handleSubmit}>
          {submit.error ? (
            <div className="form-span">
              <Alert tone="danger" title="Não foi possível concluir">
                {submit.error.message}
              </Alert>
            </div>
          ) : null}
          <FormField
            label="Nome do tenant"
            name="tenant_name"
            required
            defaultValue={progress.data.data.tenant_name}
          />
          <FormField
            label="Identificador do tenant"
            name="tenant_slug"
            pattern="[a-z0-9-]+"
            required
            defaultValue={progress.data.data.tenant_slug}
          />
          <FormField label="Grupo econômico (opcional)" name="economic_group_name" />
          <FormField label="Razão social" name="company_legal_name" required />
          <FormField label="Nome fantasia" name="company_trade_name" required />
          <FormField
            label="Identificador da empresa"
            name="company_slug"
            pattern="[a-z0-9-]+"
            required
          />
          <FormField label="Primeira filial" name="branch_name" required />
          <FormField
            label="Identificador da filial"
            name="branch_slug"
            pattern="[a-z0-9-]+"
            required
          />
          <SelectField label="Termos vigentes" name="terms_version_id" required>
            <option value="">Selecione</option>
            {terms.data.map((term) => (
              <option key={term.id} value={term.id}>
                {term.document_type} · {term.version}
              </option>
            ))}
          </SelectField>
          <label className="check-field">
            <input type="checkbox" name="accept_terms" required />
            <span>Li e aceito os termos versionados selecionados.</span>
          </label>
          <div className="form-span">
            <button className="button" disabled={submit.pending}>
              {submit.pending ? "Configurando…" : "Concluir onboarding"}
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
