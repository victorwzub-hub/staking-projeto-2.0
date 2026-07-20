"use client";

import type { MessageResponse, Session } from "@pharma/contracts";

import { Alert } from "@/components/ui/alert";
import { EmptyState, LoadingState, PageHeader } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";
import { useApi } from "@/lib/http/use-api";

export default function SessionsPage() {
  const sessions = useApi<Session[]>("sessions");
  const submit = useSubmit<MessageResponse>();
  const auth = useAuth();
  async function revoke(id: string) {
    if (!confirm("Encerrar esta sessão?")) return;
    const result = await submit.run(() => apiJson(`sessions/${id}`, "DELETE"));
    if (result) {
      await sessions.reload();
      await auth.refresh();
    }
  }
  async function revokeAll() {
    if (!confirm("Encerrar todas as sessões, inclusive esta?")) return;
    await submit.run(() => apiJson("sessions?include_current=true", "DELETE"));
    await auth.refresh();
    location.assign("/login");
  }
  return (
    <>
      <PageHeader
        eyebrow="Conta"
        title="Sessões ativas"
        description="Revogue dispositivos individualmente ou encerre todos os acessos."
        action={
          <button className="button button-danger" onClick={revokeAll}>
            Encerrar todas
          </button>
        }
      />
      {submit.error ? (
        <Alert tone="danger" title="Operação não concluída">
          {submit.error.message}
        </Alert>
      ) : null}
      {sessions.status === "loading" ? (
        <LoadingState />
      ) : sessions.status === "error" ? (
        <Alert tone="danger" title="Sessões indisponíveis">
          {sessions.error.message}
        </Alert>
      ) : sessions.data.length === 0 ? (
        <EmptyState title="Nenhuma sessão" description="Não há sessões para exibir." />
      ) : (
        <div className="content-card table-wrap">
          <table>
            <thead>
              <tr>
                <th>Dispositivo</th>
                <th>Última atividade</th>
                <th>Expiração</th>
                <th>Estado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {sessions.data.map((item) => (
                <tr key={item.id}>
                  <td>{item.user_agent ?? "Não identificado"}</td>
                  <td>{new Date(item.last_seen_at).toLocaleString("pt-BR")}</td>
                  <td>{new Date(item.expires_at).toLocaleString("pt-BR")}</td>
                  <td>
                    {item.current ? <span className="badge badge-success">Atual</span> : "Ativa"}
                  </td>
                  <td>
                    {!item.current ? (
                      <button className="link-button" onClick={() => revoke(item.id)}>
                        Revogar
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
