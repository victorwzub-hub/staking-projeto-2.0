import { ApiStatus } from "@/components/api-status";

const foundations = [
  "Next.js com TypeScript estrito",
  "FastAPI com API versionada",
  "PostgreSQL e SQLAlchemy 2",
  "Redis e Dramatiq",
  "Health, readiness e correlation ID",
  "Testes e integração contínua",
];

export default function HomePage() {
  return (
    <section className="container hero">
      <div className="hero-copy">
        <div className="eyebrow">PLATAFORMA B2B</div>
        <h1>Base pronta para evoluir com segurança.</h1>
        <p className="lead">
          Esta entrega contém somente a fundação técnica. Autenticação, billing, dashboards, regras
          farmacêuticas, Machine Learning e LLM permanecem intencionalmente fora desta fase.
        </p>
      </div>

      <div className="foundation-grid">
        <section className="foundation-card" aria-labelledby="foundation-title">
          <div>
            <p className="card-label">ESCOPO DESTA ENTREGA</p>
            <h2 id="foundation-title">Fundação técnica configurada</h2>
          </div>
          <ul>
            {foundations.map((foundation) => (
              <li key={foundation}>{foundation}</li>
            ))}
          </ul>
        </section>

        <ApiStatus />
      </div>
    </section>
  );
}
