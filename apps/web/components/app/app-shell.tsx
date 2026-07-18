"use client";

import type { MessageResponse } from "@pharma/contracts";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/lib/auth/auth-context";
import { apiJson } from "@/lib/http/client";

const navigation = [
  ["/app", "Visão geral", null],
  ["/app/tenant", "Tenant", "tenant.read"],
  ["/app/economic-groups", "Grupos econômicos", "company.read"],
  ["/app/companies", "Empresas", "company.read"],
  ["/app/branches", "Filiais", "branch.read"],
  ["/app/users", "Usuários", "user.read"],
  ["/app/invitations", "Convites", "user.invite"],
  ["/app/teams", "Equipes", "user.read"],
  ["/app/roles", "Papéis", "role.read"],
  ["/app/permissions", "Permissões", "role.read"],
  ["/app/audit", "Auditoria", "audit.read"],
  ["/app/integrations", "Integrações", "integration.view"],
  ["/app/security", "Segurança", null],
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const auth = useAuth();
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const current = auth.me?.contexts.find(
    (context) => context.tenant_id === auth.me?.active_session.active_tenant_id,
  );

  async function signOut() {
    setSigningOut(true);
    try {
      await apiJson<MessageResponse>("auth/logout", "POST");
    } finally {
      await auth.refresh();
      router.replace("/login");
      setSigningOut(false);
    }
  }

  return (
    <div className="app-frame">
      <aside
        className={`app-sidebar ${open ? "app-sidebar-open" : ""}`}
        aria-label="Navegação principal"
      >
        <div className="sidebar-brand">
          <span className="brand-mark" aria-hidden="true">
            PI
          </span>
          <div>
            <strong>Pharma Intelligence</strong>
            <small>Identidade e segurança</small>
          </div>
        </div>
        <nav className="sidebar-nav">
          {auth.me?.user.is_platform_admin ? (
            <Link
              href="/app/platform"
              className={pathname.startsWith("/app/platform") ? "active" : ""}
            >
              Administração global
            </Link>
          ) : null}
          {navigation.map(([href, label, permission]) => {
            if (permission && !auth.hasPermission(permission)) return null;
            const active = href === "/app" ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={active ? "active" : ""}
                onClick={() => setOpen(false)}
              >
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <Link href="/app/profile">{auth.me?.user.display_name ?? auth.me?.user.email}</Link>
          <button
            className="button button-quiet"
            type="button"
            onClick={signOut}
            disabled={signingOut}
          >
            {signingOut ? "Encerrando…" : "Sair"}
          </button>
        </div>
      </aside>
      <div className="app-main">
        <header className="app-topbar">
          <button
            className="menu-button"
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            aria-controls="app-sidebar"
          >
            Menu
          </button>
          <div className="context-summary">
            <span>Contexto ativo</span>
            <strong>{current?.tenant_name ?? "Nenhum tenant selecionado"}</strong>
          </div>
          <Link className="button button-secondary button-small" href="/app/select-context">
            Trocar contexto
          </Link>
        </header>
        <main className="app-content">{children}</main>
      </div>
    </div>
  );
}
