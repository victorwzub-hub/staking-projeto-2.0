"use client";

import type { MessageResponse } from "@pharma/contracts";
import { useRouter } from "next/navigation";
import { FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { SelectField } from "@/components/ui/form-field";
import { PageHeader } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";

export default function SelectContextPage() {
  const auth = useAuth();
  const submit = useSubmit<MessageResponse>();
  const router = useRouter();
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const result = await submit.run(() =>
      apiJson("me/context", "POST", {
        tenant_id: form.get("tenant_id"),
        company_id: form.get("company_id") || null,
        branch_id: form.get("branch_id") || null,
      }),
    );
    if (result) {
      await auth.refresh();
      router.replace("/app");
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="Contexto seguro"
        title="Trocar tenant, empresa ou filial"
        description="O servidor valida membership e escopo antes de persistir o novo contexto na sessão."
      />
      <form className="content-card form-stack" onSubmit={handleSubmit}>
        {submit.error ? (
          <Alert tone="danger" title="Acesso não autorizado">
            {submit.error.message}
          </Alert>
        ) : null}
        <SelectField
          label="Tenant"
          name="tenant_id"
          defaultValue={auth.me?.active_session.active_tenant_id ?? ""}
          required
        >
          <option value="">Selecione</option>
          {auth.me?.contexts.map((context) => (
            <option key={context.tenant_id} value={context.tenant_id}>
              {context.tenant_name}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Empresa (opcional)"
          name="company_id"
          defaultValue={auth.me?.active_session.active_company_id ?? ""}
        >
          <option value="">Todas</option>
          {auth.me?.contexts
            .flatMap((context) => context.companies)
            .map((company) => (
              <option key={company.id} value={company.id}>
                {company.name}
              </option>
            ))}
        </SelectField>
        <SelectField
          label="Filial (opcional)"
          name="branch_id"
          defaultValue={auth.me?.active_session.active_branch_id ?? ""}
        >
          <option value="">Todas</option>
          {auth.me?.contexts
            .flatMap((context) => context.companies.flatMap((company) => company.branches))
            .map((branch) => (
              <option key={branch.id} value={branch.id}>
                {branch.name}
              </option>
            ))}
        </SelectField>
        <button className="button" disabled={submit.pending}>
          {submit.pending ? "Validando…" : "Aplicar contexto"}
        </button>
      </form>
    </>
  );
}
