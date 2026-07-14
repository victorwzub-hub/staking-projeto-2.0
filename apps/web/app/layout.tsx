import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pharma Intelligence SaaS",
  description: "Fundação técnica da plataforma de inteligência para farmácias.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body>
        <header className="site-header">
          <div className="container header-content">
            <span className="brand">Pharma Intelligence</span>
            <span className="phase">Fundação técnica · Fase 1.1</span>
          </div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
