"use client";

import type { Company } from "@pharma/contracts";
import { FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { FormField } from "@/components/ui/form-field";
import { EmptyState, LoadingState, PageHeader } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";
import { useApi } from "@/lib/http/use-api";

export default function CompaniesPage() {
  const auth = useAuth();
  const companies = useApi<Company[]>("companies");
  const submit = useSubmit<Company>();
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const result = await submit.run(() =>
      apiJson("companies", "POST", {
        legal_name: form.get("legal_name"),
        trade_name: form.get("trade_name"),
        slug: form.get("slug"),
        economic_group_id: null,
      }),
    );
    if (result) {
      formElement.reset();
      await companies.reload();
    }
  }
  async function update(item: Company) {
    const tradeName = prompt("Novo nome fantasia:", item.trade_name);
    if (!tradeName || tradeName === item.trade_name) return;
    await submit.run(() =>
      apiJson(`companies/${item.id}`, "PATCH", {
        trade_name: tradeName,
        legal_name: null,
        status: null,
        expected_version: item.version,
      }),
    );
    await companies.reload();
  }
  async function archive(item: Company) {
    if (!confirm(`Arquivar ${item.trade_name}?`)) return;
    await submit.run(() =>
      apiJson(`companies/${item.id}`, "DELETE", { expected_version: item.version }),
    );
    await companies.reload();
  }
  return (
    <>
      <PageHeader
        eyebrow="Organização"
        title="Empresas"
        description="Empresas sempre pertencem ao tenant ativo e são filtradas por RLS."
      />
      {auth.hasPermission("company.create") ? (
        <form className="content-card form-grid" onSubmit={create}>
          <h2 className="form-span">Nova empresa</h2>
          {submit.error ? (
            <div className="form-span">
              <Alert title="Operação não concluída">{submit.error.message}</Alert>
            </div>
          ) : null}
          <FormField label="Razão social" name="legal_name" required />
          <FormField label="Nome fantasia" name="trade_name" required />
          <FormField label="Identificador" name="slug" pattern="[a-z0-9-]+" required />
          <div className="form-span">
            <button className="button" disabled={submit.pending}>
              Criar empresa
            </button>
          </div>
        </form>
      ) : null}
      <section className="content-card">
        <h2>Empresas do tenant</h2>
        {companies.status === "loading" ? (
          <LoadingState />
        ) : companies.status === "error" ? (
          <Alert title="Empresas indisponíveis">{companies.error.message}</Alert>
        ) : companies.data.length === 0 ? (
          <EmptyState
            title="Nenhuma empresa"
            description="Crie a primeira empresa autorizada deste tenant."
          />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Nome</th>
                  <th>Razão social</th>
                  <th>Status</th>
                  <th>Versão</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {companies.data.map((item) => (
                  <tr key={item.id}>
                    <td>{item.trade_name}</td>
                    <td>{item.legal_name}</td>
                    <td>
                      <span className="badge">{item.status}</span>
                    </td>
                    <td>{item.version}</td>
                    <td>
                      <div className="table-actions">
                        {auth.hasPermission("company.update") && item.status !== "archived" ? (
                          <button className="link-button" onClick={() => update(item)}>
                            Editar
                          </button>
                        ) : null}
                        {auth.hasPermission("company.delete") && item.status !== "archived" ? (
                          <button className="link-button danger" onClick={() => archive(item)}>
                            Arquivar
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
