"use client";

import type { MessageResponse, SecurityEvent } from "@pharma/contracts";
import Link from "next/link";
import { FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { FormField } from "@/components/ui/form-field";
import { EmptyState, LoadingState, PageHeader } from "@/components/ui/page-state";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";
import { useApi } from "@/lib/http/use-api";

export default function SecurityPage() {
  const events = useApi<SecurityEvent[]>("me/security-events");
  const submit = useSubmit<MessageResponse>();
  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const result = await submit.run(() =>
      apiJson("auth/change-password", "POST", {
        current_password: form.get("current_password"),
        new_password: form.get("new_password"),
      }),
    );
    if (result) formElement.reset();
  }
  return (
    <>
      <PageHeader
        eyebrow="Conta"
        title="Segurança"
        description="Senha, sessões e eventos relevantes da identidade global."
        action={
          <Link className="button button-secondary" href="/app/sessions">
            Sessões ativas
          </Link>
        }
      />
      <section className="content-card">
        <h2>Alterar senha</h2>
        <form className="form-grid" onSubmit={changePassword}>
          {submit.error ? (
            <div className="form-span">
              <Alert tone="danger" title="Senha não alterada">
                {submit.error.message}
              </Alert>
            </div>
          ) : null}
          {submit.data ? (
            <div className="form-span">
              <Alert tone="success" title="Senha alterada">
                As demais sessões foram revogadas.
              </Alert>
            </div>
          ) : null}
          <FormField
            label="Senha atual"
            name="current_password"
            type="password"
            autoComplete="current-password"
            required
          />
          <FormField
            label="Nova senha"
            name="new_password"
            type="password"
            minLength={12}
            autoComplete="new-password"
            required
          />
          <div className="form-span">
            <button className="button" disabled={submit.pending}>
              {submit.pending ? "Alterando…" : "Alterar senha"}
            </button>
          </div>
        </form>
      </section>
      <section className="content-card">
        <h2>Eventos recentes</h2>
        {events.status === "loading" ? (
          <LoadingState />
        ) : events.status === "error" ? (
          <Alert tone="danger" title="Eventos indisponíveis">
            {events.error.message}
          </Alert>
        ) : events.data.length === 0 ? (
          <EmptyState
            title="Nenhum evento"
            description="Ainda não há eventos de segurança para exibir."
          />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Evento</th>
                  <th>Resultado</th>
                  <th>Data</th>
                  <th>Correlation ID</th>
                </tr>
              </thead>
              <tbody>
                {events.data.map((item) => (
                  <tr key={item.id}>
                    <td>{item.event_type}</td>
                    <td>
                      <span className="badge">{item.outcome}</span>
                    </td>
                    <td>{new Date(item.created_at).toLocaleString("pt-BR")}</td>
                    <td>
                      <code>{item.correlation_id ?? "—"}</code>
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
