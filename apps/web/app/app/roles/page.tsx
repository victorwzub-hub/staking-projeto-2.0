"use client";

import type {
  Membership,
  MessageResponse,
  Permission,
  Role,
  RoleAssignment,
} from "@pharma/contracts";
import { FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { FormField, SelectField } from "@/components/ui/form-field";
import { EmptyState, LoadingState, PageHeader } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";
import { useApi } from "@/lib/http/use-api";

export default function RolesPage() {
  const auth = useAuth();
  const roles = useApi<Role[]>("roles");
  const permissions = useApi<Permission[]>("permissions");
  const memberships = useApi<Membership[]>("memberships");
  const assignments = useApi<RoleAssignment[]>("roles/assignments");
  const submit = useSubmit<Role | MessageResponse>();

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const result = await submit.run(() =>
      apiJson<Role>("roles", "POST", {
        name: form.get("name"),
        slug: form.get("slug"),
        scope: form.get("scope"),
        description: form.get("description") || null,
        permission_keys: form.getAll("permission_keys"),
      }),
    );
    if (result) {
      event.currentTarget.reset();
      await roles.reload();
    }
  }

  async function assign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const result = await submit.run(() =>
      apiJson<MessageResponse>("roles/assignments", "POST", {
        membership_id: form.get("membership_id"),
        role_id: form.get("role_id"),
        company_id: null,
        branch_id: null,
      }),
    );
    if (result) {
      event.currentTarget.reset();
      await assignments.reload();
    }
  }

  async function removeAssignment(id: string) {
    if (!confirm("Remover esta atribuição de papel?")) return;
    await submit.run(() => apiJson<MessageResponse>(`roles/assignments/${id}`, "DELETE"));
    await assignments.reload();
  }

  async function update(item: Role) {
    const name = prompt("Novo nome do papel:", item.name);
    if (!name || name === item.name) return;
    await submit.run(() =>
      apiJson<Role>(`roles/${item.id}`, "PATCH", {
        name,
        description: null,
        permission_keys: null,
        expected_version: item.version,
      }),
    );
    await roles.reload();
  }

  async function remove(item: Role) {
    if (!confirm(`Excluir o papel ${item.name}?`)) return;
    await submit.run(() => apiJson<MessageResponse>(`roles/${item.id}`, "DELETE"));
    await roles.reload();
  }

  return (
    <>
      <PageHeader
        eyebrow="RBAC"
        title="Papéis"
        description="Papéis de sistema são imutáveis; papéis personalizados só podem receber permissões delegáveis pelo ator."
      />
      {submit.error ? <Alert title="Operação recusada">{submit.error.message}</Alert> : null}

      {auth.hasPermission("role.create") && permissions.status === "success" ? (
        <form className="content-card form-grid" onSubmit={create}>
          <h2 className="form-span">Novo papel personalizado</h2>
          <FormField label="Nome" name="name" required />
          <FormField label="Identificador" name="slug" pattern="[a-z0-9-]+" required />
          <SelectField label="Escopo" name="scope" required>
            <option value="tenant">Tenant</option>
            <option value="company">Empresa</option>
            <option value="branch">Filial</option>
          </SelectField>
          <FormField label="Descrição" name="description" />
          <fieldset className="form-span permission-selector">
            <legend>Permissões delegáveis</legend>
            {permissions.data
              .filter((item) => item.scope !== "platform")
              .map((item) => (
                <label key={item.id}>
                  <input type="checkbox" name="permission_keys" value={item.key} />{" "}
                  <code>{item.key}</code>
                </label>
              ))}
          </fieldset>
          <div className="form-span">
            <button className="button" disabled={submit.pending}>
              Criar papel
            </button>
          </div>
        </form>
      ) : null}

      {auth.hasPermission("role.assign") &&
      memberships.status === "success" &&
      roles.status === "success" ? (
        <form className="content-card form-grid" onSubmit={assign}>
          <h2 className="form-span">Atribuir papel no tenant</h2>
          <SelectField label="Membership" name="membership_id" required>
            <option value="">Selecione</option>
            {memberships.data
              .filter((item) => item.status === "active")
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.display_name} · {item.email}
                </option>
              ))}
          </SelectField>
          <SelectField label="Papel" name="role_id" required>
            <option value="">Selecione</option>
            {roles.data
              .filter((item) => item.scope === "tenant" && item.slug !== "platform_admin")
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
          </SelectField>
          <div className="form-span">
            <button className="button" disabled={submit.pending}>
              Atribuir papel
            </button>
          </div>
        </form>
      ) : null}

      <section className="content-card">
        <h2>Atribuições ativas</h2>
        {assignments.status === "loading" ? (
          <LoadingState />
        ) : assignments.status === "error" ? (
          <Alert title="Atribuições indisponíveis">{assignments.error.message}</Alert>
        ) : assignments.data.length === 0 ? (
          <EmptyState
            title="Nenhuma atribuição"
            description="As atribuições de papéis aparecerão aqui."
          />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Usuário</th>
                  <th>Papel</th>
                  <th>Escopo</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {assignments.data.map((item) => (
                  <tr key={item.id}>
                    <td>
                      {memberships.status === "success"
                        ? (memberships.data.find(
                            (membership) => membership.id === item.membership_id,
                          )?.display_name ?? item.membership_id)
                        : item.membership_id}
                    </td>
                    <td>
                      {roles.status === "success"
                        ? (roles.data.find((role) => role.id === item.role_id)?.name ??
                          item.role_id)
                        : item.role_id}
                    </td>
                    <td>{item.branch_id ? "Filial" : item.company_id ? "Empresa" : "Tenant"}</td>
                    <td>
                      {auth.hasPermission("role.assign") ? (
                        <button
                          className="link-button danger"
                          onClick={() => removeAssignment(item.id)}
                        >
                          Remover
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="content-card">
        <h2>Papéis disponíveis</h2>
        {roles.status === "loading" ? (
          <LoadingState />
        ) : roles.status === "error" ? (
          <Alert title="Papéis indisponíveis">{roles.error.message}</Alert>
        ) : roles.data.length === 0 ? (
          <EmptyState
            title="Nenhum papel"
            description="O catálogo inicial ainda não foi provisionado."
          />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Papel</th>
                  <th>Escopo</th>
                  <th>Tipo</th>
                  <th>Permissões</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {roles.data.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.name}</strong>
                      <br />
                      <code>{item.slug}</code>
                    </td>
                    <td>{item.scope}</td>
                    <td>{item.is_system ? "Sistema" : "Personalizado"}</td>
                    <td>{item.permissions.length}</td>
                    <td>
                      {!item.is_system ? (
                        <div className="table-actions">
                          {auth.hasPermission("role.update") ? (
                            <button className="link-button" onClick={() => update(item)}>
                              Editar
                            </button>
                          ) : null}
                          {auth.hasPermission("role.delete") ? (
                            <button className="link-button danger" onClick={() => remove(item)}>
                              Excluir
                            </button>
                          ) : null}
                        </div>
                      ) : null}
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
