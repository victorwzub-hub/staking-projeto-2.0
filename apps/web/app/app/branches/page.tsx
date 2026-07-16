"use client";

import type { Branch, Company } from "@pharma/contracts";
import { FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { FormField, SelectField } from "@/components/ui/form-field";
import { EmptyState, LoadingState, PageHeader } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";
import { useApi } from "@/lib/http/use-api";

export default function BranchesPage() {
  const auth = useAuth();
  const branches = useApi<Branch[]>("branches");
  const companies = useApi<Company[]>("companies");
  const submit = useSubmit<Branch>();
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const result = await submit.run(() =>
      apiJson("branches", "POST", {
        company_id: form.get("company_id"),
        name: form.get("name"),
        slug: form.get("slug"),
      }),
    );
    if (result) {
      event.currentTarget.reset();
      await branches.reload();
    }
  }
  async function update(item: Branch) {
    const name = prompt("Novo nome da filial:", item.name);
    if (!name || name === item.name) return;
    await submit.run(() =>
      apiJson(`branches/${item.id}`, "PATCH", {
        name,
        status: null,
        expected_version: item.version,
      }),
    );
    await branches.reload();
  }
  async function archive(item: Branch) {
    if (!confirm(`Arquivar ${item.name}?`)) return;
    await submit.run(() =>
      apiJson(`branches/${item.id}`, "DELETE", { expected_version: item.version }),
    );
    await branches.reload();
  }
  return (
    <>
      <PageHeader
        eyebrow="Organização"
        title="Filiais"
        description="A filial deve pertencer a uma empresa do mesmo tenant; o backend valida essa hierarquia."
      />
      {auth.hasPermission("branch.create") && companies.status === "success" ? (
        <form className="content-card form-grid" onSubmit={create}>
          <h2 className="form-span">Nova filial</h2>
          {submit.error ? (
            <div className="form-span">
              <Alert title="Operação não concluída">{submit.error.message}</Alert>
            </div>
          ) : null}
          <SelectField label="Empresa" name="company_id" required>
            <option value="">Selecione</option>
            {companies.data
              .filter((item) => item.status === "active")
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.trade_name}
                </option>
              ))}
          </SelectField>
          <FormField label="Nome da filial" name="name" required />
          <FormField label="Identificador" name="slug" pattern="[a-z0-9-]+" required />
          <div className="form-span">
            <button className="button" disabled={submit.pending}>
              Criar filial
            </button>
          </div>
        </form>
      ) : null}
      <section className="content-card">
        <h2>Filiais do tenant</h2>
        {branches.status === "loading" ? (
          <LoadingState />
        ) : branches.status === "error" ? (
          <Alert title="Filiais indisponíveis">{branches.error.message}</Alert>
        ) : branches.data.length === 0 ? (
          <EmptyState
            title="Nenhuma filial"
            description="Crie uma filial vinculada a uma empresa ativa."
          />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Filial</th>
                  <th>Empresa</th>
                  <th>Status</th>
                  <th>Versão</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {branches.data.map((item) => (
                  <tr key={item.id}>
                    <td>{item.name}</td>
                    <td>
                      {companies.status === "success"
                        ? (companies.data.find((company) => company.id === item.company_id)
                            ?.trade_name ?? "—")
                        : item.company_id}
                    </td>
                    <td>
                      <span className="badge">{item.status}</span>
                    </td>
                    <td>{item.version}</td>
                    <td>
                      <div className="table-actions">
                        {auth.hasPermission("branch.update") && item.status !== "archived" ? (
                          <button className="link-button" onClick={() => update(item)}>
                            Editar
                          </button>
                        ) : null}
                        {auth.hasPermission("branch.delete") && item.status !== "archived" ? (
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
