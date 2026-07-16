"use client";

import type { AuditEvent, Page } from "@pharma/contracts";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { EmptyState, LoadingState, PageHeader } from "@/components/ui/page-state";
import { useApi } from "@/lib/http/use-api";

export default function AuditPage() {
  const [offset, setOffset] = useState(0);
  const events = useApi<Page<AuditEvent>>(`audit-events?limit=25&offset=${offset}`);
  return (
    <>
      <PageHeader
        eyebrow="Segurança operacional"
        title="Auditoria"
        description="Registro append-only, sanitizado e isolado pelo tenant ativo."
      />
      {events.status === "loading" ? (
        <LoadingState />
      ) : events.status === "error" ? (
        <Alert title="Auditoria indisponível">{events.error.message}</Alert>
      ) : events.data.items.length === 0 ? (
        <EmptyState
          title="Nenhum evento"
          description="Eventos administrativos e de autorização aparecerão aqui."
        />
      ) : (
        <section className="content-card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Ação</th>
                  <th>Resultado</th>
                  <th>Recurso</th>
                  <th>Correlation ID</th>
                </tr>
              </thead>
              <tbody>
                {events.data.items.map((item) => (
                  <tr key={item.id}>
                    <td>{new Date(item.created_at).toLocaleString("pt-BR")}</td>
                    <td>
                      <code>{item.action}</code>
                    </td>
                    <td>
                      <span className="badge">{item.outcome}</span>
                    </td>
                    <td>
                      {item.resource_type ?? "—"}
                      {item.resource_id ? ` · ${item.resource_id}` : ""}
                    </td>
                    <td>
                      <code>{item.correlation_id ?? "—"}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <button
              className="button button-secondary"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 25))}
            >
              Anterior
            </button>
            <span>
              {offset + 1}–{Math.min(offset + 25, events.data.total)} de {events.data.total}
            </span>
            <button
              className="button button-secondary"
              disabled={offset + 25 >= events.data.total}
              onClick={() => setOffset(offset + 25)}
            >
              Próxima
            </button>
          </div>
        </section>
      )}
    </>
  );
}
