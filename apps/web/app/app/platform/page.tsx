"use client";

import type { Page, PlatformUser, Tenant } from "@pharma/contracts";

import { Alert } from "@/components/ui/alert";
import { LoadingState, PageHeader } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";
import { useApi } from "@/lib/http/use-api";

export default function PlatformPage() {
  const auth = useAuth();
  const tenants = useApi<Page<Tenant>>("platform/tenants?limit=50");
  const users = useApi<Page<PlatformUser>>("platform/users?limit=50");
  const submit = useSubmit<PlatformUser>();

  if (!auth.me?.user.is_platform_admin) {
    return <Alert title="Acesso restrito">Esta área exige administração da plataforma.</Alert>;
  }

  async function changeStatus(user: PlatformUser) {
    const next = user.status === "active" ? "suspended" : "active";
    const reason = window.prompt(`Justificativa para alterar o status para ${next}:`);
    if (!reason || reason.trim().length < 8) return;
    const result = await submit.run(() =>
      apiJson<PlatformUser>(`platform/users/${user.id}/status`, "PATCH", {
        status: next,
        expected_version: user.version,
        reason,
      }),
    );
    if (result) await users.reload();
  }

  return (
    <>
      <PageHeader
        eyebrow="Administração da plataforma"
        title="Operação global"
        description="Visibilidade global reservada ao platform_admin, com justificativa e auditoria para alterações."
      />
      {submit.error ? <Alert title="Alteração recusada">{submit.error.message}</Alert> : null}
      <section className="metric-grid">
        <article className="metric-card">
          <span>Tenants</span>
          <strong>{tenants.status === "success" ? tenants.data.total : "—"}</strong>
        </article>
        <article className="metric-card">
          <span>Usuários globais</span>
          <strong>{users.status === "success" ? users.data.total : "—"}</strong>
        </article>
      </section>
      <section className="content-card">
        <h2>Tenants recentes</h2>
        {tenants.status === "loading" ? (
          <LoadingState />
        ) : tenants.status === "error" ? (
          <Alert title="Tenants indisponíveis">{tenants.error.message}</Alert>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Tenant</th>
                  <th>Status</th>
                  <th>Criado</th>
                </tr>
              </thead>
              <tbody>
                {tenants.data.items.map((tenant) => (
                  <tr key={tenant.id}>
                    <td>
                      {tenant.name}
                      <br />
                      <code>{tenant.slug}</code>
                    </td>
                    <td>
                      <span className="badge">{tenant.status}</span>
                    </td>
                    <td>{new Date(tenant.created_at).toLocaleString("pt-BR")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="content-card">
        <h2>Usuários globais</h2>
        {users.status === "loading" ? (
          <LoadingState />
        ) : users.status === "error" ? (
          <Alert title="Usuários indisponíveis">{users.error.message}</Alert>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Usuário</th>
                  <th>Status</th>
                  <th>Tipo</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {users.data.items.map((user) => (
                  <tr key={user.id}>
                    <td>
                      {user.display_name}
                      <br />
                      <small>{user.email}</small>
                    </td>
                    <td>
                      <span className="badge">{user.status}</span>
                    </td>
                    <td>{user.is_platform_admin ? "Platform admin" : "Usuário"}</td>
                    <td>
                      <button
                        className="link-button"
                        disabled={user.id === auth.me?.user.id}
                        onClick={() => changeStatus(user)}
                      >
                        {user.status === "active" ? "Suspender" : "Ativar"}
                      </button>
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
