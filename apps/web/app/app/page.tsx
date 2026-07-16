"use client";

import Link from "next/link";

import { Alert } from "@/components/ui/alert";
import { PageHeader } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";

export default function ApplicationHomePage() {
  const { me } = useAuth();
  const active = me?.contexts.find((item) => item.tenant_id === me.active_session.active_tenant_id);
  return (
    <>
      <PageHeader
        eyebrow="Núcleo de identidade"
        title={`Olá, ${me?.user.display_name ?? "usuário"}`}
        description="Gerencie o contexto organizacional, acessos e segurança da conta. Módulos analíticos serão adicionados nas próximas fases."
      />
      {!active ? (
        <Alert tone="warning" title="Selecione um contexto">
          Escolha um tenant autorizado antes de acessar recursos organizacionais.{" "}
          <Link href="/app/select-context">Selecionar agora</Link>
        </Alert>
      ) : null}
      <section className="metric-grid" aria-label="Resumo da identidade">
        <article className="metric-card">
          <span>Tenant ativo</span>
          <strong>{active?.tenant_name ?? "Não selecionado"}</strong>
        </article>
        <article className="metric-card">
          <span>Memberships</span>
          <strong>{me?.contexts.length ?? 0}</strong>
        </article>
        <article className="metric-card">
          <span>Permissões efetivas</span>
          <strong>{me?.permissions.length ?? 0}</strong>
        </article>
        <article className="metric-card">
          <span>Sessão expira</span>
          <strong>
            {me ? new Date(me.active_session.expires_at).toLocaleString("pt-BR") : "—"}
          </strong>
        </article>
      </section>
      <section className="content-card">
        <h2>Ações de segurança</h2>
        <div className="action-grid">
          <Link href="/app/security">Revisar eventos de segurança</Link>
          <Link href="/app/sessions">Gerenciar sessões ativas</Link>
          <Link href="/app/profile">Atualizar perfil</Link>
          <Link href="/app/select-context">Trocar organização</Link>
        </div>
      </section>
    </>
  );
}
