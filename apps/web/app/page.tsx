import Link from "next/link";

import { ApiStatus } from "@/components/api-status";

const capabilities = [
  "Identidade global e verificação de e-mail",
  "Sessões opacas e proteção CSRF",
  "Tenant, empresas, filiais e memberships",
  "RBAC deny-by-default e PostgreSQL RLS",
  "Onboarding, convites e auditoria append-only",
  "Worker de e-mail com adapter de desenvolvimento",
];

export default function HomePage() {
  return (
    <main className="marketing-page">
      <header className="marketing-header container">
        <span className="brand">Pharma Intelligence</span>
        <nav aria-label="Acesso">
          <Link href="/login">Entrar</Link>
          <Link className="button button-small" href="/register">
            Criar conta
          </Link>
        </nav>
      </header>
      <section className="container hero">
        <div className="hero-copy">
          <p className="eyebrow">PLATAFORMA B2B MULTI-TENANT</p>
          <h1>Identidade e acesso preparados para um SaaS de alta criticidade.</h1>
          <p className="lead">
            A Fase 2 estabelece o núcleo seguro para usuários, organizações, sessões, permissões e
            auditoria. Os módulos analíticos de farmácia permanecem fora deste escopo.
          </p>
          <div className="hero-actions">
            <Link className="button" href="/register">
              Iniciar onboarding
            </Link>
            <Link className="button button-secondary" href="/login">
              Acessar conta
            </Link>
          </div>
        </div>
        <div className="foundation-grid">
          <section className="foundation-card" aria-labelledby="capabilities-title">
            <p className="card-label">NÚCLEO IMPLEMENTADO</p>
            <h2 id="capabilities-title">Segurança em defesa em profundidade</h2>
            <ul>
              {capabilities.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
          <ApiStatus />
        </div>
      </section>
    </main>
  );
}
