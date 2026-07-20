"use client";

import type { EconomicGroup, MessageResponse } from "@pharma/contracts";
import { FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { FormField } from "@/components/ui/form-field";
import { EmptyState, LoadingState, PageHeader } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";
import { useApi } from "@/lib/http/use-api";

export default function EconomicGroupsPage() {
  const auth = useAuth();
  const groups = useApi<EconomicGroup[]>("economic-groups");
  const submit = useSubmit<EconomicGroup | MessageResponse>();
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const result = await submit.run(() =>
      apiJson<EconomicGroup>("economic-groups", "POST", { name: form.get("name") }),
    );
    if (result) {
      formElement.reset();
      await groups.reload();
    }
  }
  async function rename(item: EconomicGroup) {
    const name = prompt("Novo nome do grupo econômico:", item.name);
    if (!name || name === item.name) return;
    await submit.run(() =>
      apiJson(`economic-groups/${item.id}`, "PATCH", {
        name,
        status: null,
        expected_version: item.version,
      }),
    );
    await groups.reload();
  }
  async function archive(item: EconomicGroup) {
    if (!confirm(`Arquivar ${item.name}?`)) return;
    await submit.run(() =>
      apiJson(`economic-groups/${item.id}`, "DELETE", { expected_version: item.version }),
    );
    await groups.reload();
  }
  return (
    <>
      <PageHeader
        eyebrow="Organização"
        title="Grupos econômicos"
        description="Agrupe empresas relacionadas sem alterar a fronteira de isolamento do tenant."
      />
      {auth.hasPermission("company.create") ? (
        <form className="content-card form-grid" onSubmit={create}>
          <h2 className="form-span">Novo grupo</h2>
          {submit.error ? (
            <div className="form-span">
              <Alert title="Operação recusada">{submit.error.message}</Alert>
            </div>
          ) : null}
          <FormField label="Nome" name="name" required />
          <div>
            <button className="button" disabled={submit.pending}>
              Criar grupo
            </button>
          </div>
        </form>
      ) : null}
      <section className="content-card">
        {groups.status === "loading" ? (
          <LoadingState />
        ) : groups.status === "error" ? (
          <Alert title="Grupos indisponíveis">{groups.error.message}</Alert>
        ) : groups.data.length === 0 ? (
          <EmptyState title="Nenhum grupo" description="O uso de grupo econômico é opcional." />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Grupo</th>
                  <th>Status</th>
                  <th>Versão</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {groups.data.map((item) => (
                  <tr key={item.id}>
                    <td>{item.name}</td>
                    <td>
                      <span className="badge">{item.status}</span>
                    </td>
                    <td>{item.version}</td>
                    <td>
                      <div className="table-actions">
                        <button className="link-button" onClick={() => rename(item)}>
                          Renomear
                        </button>
                        <button className="link-button danger" onClick={() => archive(item)}>
                          Arquivar
                        </button>
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
