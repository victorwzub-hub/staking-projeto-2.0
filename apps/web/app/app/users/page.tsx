"use client";

import type { Membership } from "@pharma/contracts";

import { Alert } from "@/components/ui/alert";
import { EmptyState, LoadingState, PageHeader } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";
import { useApi } from "@/lib/http/use-api";

export default function UsersPage() {
  const auth = useAuth();
  const memberships = useApi<Membership[]>("users");
  const submit = useSubmit<Membership>();
  async function setStatus(item: Membership, status: "active" | "suspended" | "revoked") {
    if (!confirm(`Alterar o acesso de ${item.email} para ${status}?`)) return;
    await submit.run(() =>
      apiJson(`memberships/${item.id}`, "PATCH", { status, expected_version: item.version }),
    );
    await memberships.reload();
  }
  return (
    <>
      <PageHeader
        eyebrow="Acesso"
        title="Usuários do tenant"
        description="A identidade é global; o acesso a este tenant existe somente pela membership."
      />
      {submit.error ? <Alert title="Alteração recusada">{submit.error.message}</Alert> : null}
      <section className="content-card">
        {memberships.status === "loading" ? (
          <LoadingState />
        ) : memberships.status === "error" ? (
          <Alert title="Usuários indisponíveis">{memberships.error.message}</Alert>
        ) : memberships.data.length === 0 ? (
          <EmptyState
            title="Nenhum usuário"
            description="Convide pessoas para criar novas memberships."
          />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Usuário</th>
                  <th>Status</th>
                  <th>Papéis</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {memberships.data.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.display_name}</strong>
                      <br />
                      <small>{item.email}</small>
                    </td>
                    <td>
                      <span className="badge">{item.status}</span>
                    </td>
                    <td>{item.roles.join(", ") || "Sem papel"}</td>
                    <td>
                      {auth.hasPermission("membership.manage") ? (
                        <div className="table-actions">
                          <button className="link-button" onClick={() => setStatus(item, "active")}>
                            Ativar
                          </button>
                          <button
                            className="link-button"
                            onClick={() => setStatus(item, "suspended")}
                          >
                            Suspender
                          </button>
                          <button
                            className="link-button danger"
                            onClick={() => setStatus(item, "revoked")}
                          >
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
