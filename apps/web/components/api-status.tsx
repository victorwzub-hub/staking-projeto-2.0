"use client";

import type { HealthResponse } from "@pharma/contracts";
import { useCallback, useEffect, useState } from "react";

import { apiRequest } from "@/lib/http/client";

type ApiStatusState =
  | { kind: "loading" }
  | { kind: "success"; health: HealthResponse }
  | { kind: "error"; message: string };

function requestHealth(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("health", { cache: "no-store" });
}

export function ApiStatus() {
  const [state, setState] = useState<ApiStatusState>({ kind: "loading" });

  useEffect(() => {
    let active = true;

    void requestHealth().then(
      (health) => {
        if (active) {
          setState({ kind: "success", health });
        }
      },
      (error: unknown) => {
        if (active) {
          setState({
            kind: "error",
            message:
              error instanceof Error
                ? error.message
                : "Não foi possível confirmar a disponibilidade do serviço.",
          });
        }
      },
    );

    return () => {
      active = false;
    };
  }, []);

  const retry = useCallback(() => {
    setState({ kind: "loading" });
    void requestHealth().then(
      (health) => setState({ kind: "success", health }),
      (error: unknown) =>
        setState({
          kind: "error",
          message:
            error instanceof Error
              ? error.message
              : "Não foi possível confirmar a disponibilidade do serviço.",
        }),
    );
  }, []);

  if (state.kind === "loading") {
    return (
      <section className="api-status-card" aria-busy="true" aria-live="polite">
        <div className="api-status-heading">
          <span className="status-indicator status-indicator-loading" aria-hidden="true" />
          <div>
            <p className="card-label">CONEXÃO OPERACIONAL</p>
            <h2>Verificando conexão com a API</h2>
          </div>
        </div>
        <p className="api-status-copy">Aguardando uma resposta real do endpoint de health.</p>
      </section>
    );
  }

  if (state.kind === "error") {
    return (
      <section className="api-status-card api-status-error" role="alert" aria-live="assertive">
        <div className="api-status-heading">
          <span className="status-indicator status-indicator-error" aria-hidden="true" />
          <div>
            <p className="card-label">CONEXÃO OPERACIONAL</p>
            <h2>API indisponível</h2>
          </div>
        </div>
        <p className="api-status-copy">{state.message}</p>
        <p className="api-status-copy">Nenhum estado de sucesso foi presumido.</p>
        <button className="button" type="button" onClick={retry}>
          Tentar novamente
        </button>
      </section>
    );
  }

  return (
    <section className="api-status-card api-status-success" aria-live="polite">
      <div className="api-status-heading">
        <span className="status-indicator status-indicator-success" aria-hidden="true" />
        <div>
          <p className="card-label">CONEXÃO OPERACIONAL</p>
          <h2>API disponível</h2>
        </div>
      </div>
      <dl className="service-metadata">
        <div>
          <dt>Serviço</dt>
          <dd>{state.health.service}</dd>
        </div>
        <div>
          <dt>Versão</dt>
          <dd>{state.health.version}</dd>
        </div>
      </dl>
    </section>
  );
}
