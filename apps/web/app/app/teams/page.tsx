"use client";

import type { Membership, MessageResponse, Team } from "@pharma/contracts";
import { FormEvent, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { FormField, SelectField } from "@/components/ui/form-field";
import { EmptyState, LoadingState, PageHeader } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";
import { useApi } from "@/lib/http/use-api";

export default function TeamsPage() {
  const auth = useAuth();
  const teams = useApi<Team[]>("teams");
  const users = useApi<Membership[]>("users");
  const submit = useSubmit<Team | MessageResponse>();
  const [selected, setSelected] = useState<string>("");
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const result = await submit.run(() =>
      apiJson<Team>("teams", "POST", {
        name: form.get("name"),
        description: form.get("description") || null,
      }),
    );
    if (result) {
      formElement.reset();
      await teams.reload();
    }
  }
  async function addMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (!selected) return;
    await submit.run(() =>
      apiJson(`teams/${selected}/members`, "POST", { membership_id: form.get("membership_id") }),
    );
  }
  async function update(item: Team) {
    const name = prompt("Novo nome da equipe:", item.name);
    if (!name || name === item.name) return;
    await submit.run(() =>
      apiJson(`teams/${item.id}`, "PATCH", {
        name,
        description: item.description,
        expected_version: item.version,
      }),
    );
    await teams.reload();
  }
  async function remove(item: Team) {
    if (!confirm(`Excluir a equipe ${item.name}?`)) return;
    await submit.run(() => apiJson(`teams/${item.id}`, "DELETE"));
    await teams.reload();
  }
  return (
    <>
      <PageHeader
        eyebrow="Organização"
        title="Equipes"
        description="Agrupamento operacional de memberships dentro do tenant ativo."
      />
      {auth.hasPermission("team.create") ? (
        <form className="content-card form-grid" onSubmit={create}>
          <h2 className="form-span">Nova equipe</h2>
          {submit.error ? (
            <div className="form-span">
              <Alert title="Operação recusada">{submit.error.message}</Alert>
            </div>
          ) : null}
          <FormField label="Nome" name="name" required />
          <FormField label="Descrição" name="description" />
          <div className="form-span">
            <button className="button" disabled={submit.pending}>
              Criar equipe
            </button>
          </div>
        </form>
      ) : null}
      <section className="content-card">
        <h2>Equipes</h2>
        {teams.status === "loading" ? (
          <LoadingState />
        ) : teams.status === "error" ? (
          <Alert title="Equipes indisponíveis">{teams.error.message}</Alert>
        ) : teams.data.length === 0 ? (
          <EmptyState
            title="Nenhuma equipe"
            description="Crie uma equipe para organizar memberships."
          />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Nome</th>
                  <th>Descrição</th>
                  <th>Versão</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {teams.data.map((item) => (
                  <tr key={item.id}>
                    <td>{item.name}</td>
                    <td>{item.description ?? "—"}</td>
                    <td>{item.version}</td>
                    <td>
                      <div className="table-actions">
                        <button className="link-button" onClick={() => setSelected(item.id)}>
                          Adicionar membro
                        </button>
                        {auth.hasPermission("team.update") ? (
                          <button className="link-button" onClick={() => update(item)}>
                            Editar
                          </button>
                        ) : null}
                        {auth.hasPermission("team.delete") ? (
                          <button className="link-button danger" onClick={() => remove(item)}>
                            Excluir
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
      {selected && users.status === "success" ? (
        <form className="content-card form-grid" onSubmit={addMember}>
          <h2 className="form-span">Adicionar membership à equipe</h2>
          <SelectField label="Usuário" name="membership_id" required>
            <option value="">Selecione</option>
            {users.data
              .filter((user) => user.status === "active")
              .map((user) => (
                <option key={user.id} value={user.id}>
                  {user.display_name} · {user.email}
                </option>
              ))}
          </SelectField>
          <div>
            <button className="button" disabled={submit.pending}>
              Adicionar
            </button>
          </div>
        </form>
      ) : null}
    </>
  );
}
