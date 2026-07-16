"use client";

import type { Tenant } from "@pharma/contracts";
import { FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { FormField } from "@/components/ui/form-field";
import { LoadingState, PageHeader } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";
import { useApi } from "@/lib/http/use-api";

export default function TenantPage() {
  const auth = useAuth();
  const tenant = useApi<Tenant>("tenants/current");
  const submit = useSubmit<Tenant>();
  if (tenant.status === "loading") return <LoadingState label="Carregando tenant" />;
  if (tenant.status === "error")
    return <Alert title="Tenant indisponível">{tenant.error.message}</Alert>;
  const current = tenant.data;
  async function update(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const result = await submit.run(() =>
      apiJson<Tenant>("tenants/current", "PATCH", {
        name: form.get("name"),
        expected_version: current.version,
      }),
    );
    if (result) {
      await tenant.reload();
      await auth.refresh();
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="Organização"
        title="Tenant"
        description="Fronteira principal de isolamento dos dados e permissões."
      />
      <form className="content-card form-grid" onSubmit={update}>
        {submit.error ? (
          <div className="form-span">
            <Alert title="Tenant não atualizado">{submit.error.message}</Alert>
          </div>
        ) : null}
        <FormField
          label="Nome"
          name="name"
          defaultValue={current.name}
          disabled={!auth.hasPermission("tenant.update")}
          required
        />
        <FormField label="Identificador" value={current.slug} readOnly disabled />
        <FormField label="Status" value={current.status} readOnly disabled />
        <FormField label="Versão" value={current.version} readOnly disabled />
        {auth.hasPermission("tenant.update") ? (
          <div className="form-span">
            <button className="button" disabled={submit.pending}>
              Salvar tenant
            </button>
          </div>
        ) : null}
      </form>
    </>
  );
}
