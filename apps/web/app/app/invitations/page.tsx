"use client";

import type { Invitation, MessageResponse, Role } from "@pharma/contracts";
import { FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { FormField, SelectField } from "@/components/ui/form-field";
import { EmptyState, LoadingState, PageHeader } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";
import { useApi } from "@/lib/http/use-api";

export default function InvitationsPage() {
  const auth = useAuth();
  const invitations = useApi<Invitation[]>("invitations");
  const roles = useApi<Role[]>("roles", auth.hasPermission("role.read"));
  const submit = useSubmit<Invitation | MessageResponse>();
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const result = await submit.run(() =>
      apiJson<Invitation>("invitations", "POST", {
        email: form.get("email"),
        role_id: form.get("role_id"),
        company_id: null,
        branch_id: null,
      }),
    );
    if (result) {
      formElement.reset();
      await invitations.reload();
    }
  }
  async function resend(id: string) {
    await submit.run(() => apiJson(`invitations/${id}/resend`, "POST"));
    await invitations.reload();
  }
  async function revoke(id: string) {
    if (!confirm("Revogar este convite?")) return;
    await submit.run(() => apiJson(`invitations/${id}`, "DELETE"));
    await invitations.reload();
  }
  return (
    <>
      <PageHeader
        eyebrow="Acesso"
        title="Convites"
        description="Tokens de uso único, com hash no banco, expiração e escopo previamente autorizado."
      />
      {auth.hasPermission("user.invite") && roles.status === "success" ? (
        <form className="content-card form-grid" onSubmit={create}>
          <h2 className="form-span">Novo convite</h2>
          {submit.error ? (
            <div className="form-span">
              <Alert title="Convite não criado">{submit.error.message}</Alert>
            </div>
          ) : null}
          <FormField label="E-mail" name="email" type="email" required />
          <SelectField label="Papel inicial" name="role_id" required>
            <option value="">Selecione</option>
            {roles.data
              .filter((role) => role.scope !== "platform")
              .map((role) => (
                <option key={role.id} value={role.id}>
                  {role.name} · {role.scope}
                </option>
              ))}
          </SelectField>
          <div className="form-span">
            <button className="button" disabled={submit.pending}>
              Enviar convite
            </button>
          </div>
        </form>
      ) : null}
      <section className="content-card">
        {invitations.status === "loading" ? (
          <LoadingState />
        ) : invitations.status === "error" ? (
          <Alert title="Convites indisponíveis">{invitations.error.message}</Alert>
        ) : invitations.data.length === 0 ? (
          <EmptyState
            title="Nenhum convite"
            description="Convites ativos e históricos aparecerão aqui."
          />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>E-mail</th>
                  <th>Status</th>
                  <th>Expira</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {invitations.data.map((item) => (
                  <tr key={item.id}>
                    <td>{item.normalized_email}</td>
                    <td>
                      <span className="badge">{item.status}</span>
                    </td>
                    <td>{new Date(item.expires_at).toLocaleString("pt-BR")}</td>
                    <td>
                      {auth.hasPermission("user.invite") && item.status === "pending" ? (
                        <div className="table-actions">
                          <button className="link-button" onClick={() => resend(item.id)}>
                            Reenviar
                          </button>
                          <button className="link-button danger" onClick={() => revoke(item.id)}>
                            Revogar
                          </button>
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
