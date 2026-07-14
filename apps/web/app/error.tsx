"use client";

import { useEffect } from "react";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Unexpected frontend error", { message: error.message, digest: error.digest });
  }, [error]);

  return (
    <section className="container hero" role="alert">
      <div className="eyebrow">ERRO INESPERADO</div>
      <h1>Não foi possível carregar esta página.</h1>
      <p className="lead">Tente novamente. O identificador técnico foi preservado nos logs.</p>
      <button className="button" type="button" onClick={reset}>
        Tentar novamente
      </button>
    </section>
  );
}
