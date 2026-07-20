"use client";

import type { Permission } from "@pharma/contracts";

import { Alert } from "@/components/ui/alert";
import { EmptyState, LoadingState, PageHeader } from "@/components/ui/page-state";
import { useApi } from "@/lib/http/use-api";

export default function PermissionsPage() {
  const permissions = useApi<Permission[]>("permissions");
  return (
    <>
      <PageHeader
        eyebrow="RBAC"
        title="Catálogo de permissões"
        description="Permissões versionadas; a autorização é baseada em capacidades, não apenas no nome do papel."
      />
      {permissions.status === "loading" ? (
        <LoadingState />
      ) : permissions.status === "error" ? (
        <Alert title="Catálogo indisponível">{permissions.error.message}</Alert>
      ) : permissions.data.length === 0 ? (
        <EmptyState title="Catálogo vazio" description="Nenhuma permissão foi publicada." />
      ) : (
        <section className="permission-grid">
          {permissions.data.map((item) => (
            <article className="permission-card" key={item.id}>
              <code>{item.key}</code>
              <span className="badge">{item.scope}</span>
              <p>{item.description}</p>
              <small>Catálogo v{item.catalog_version}</small>
            </article>
          ))}
        </section>
      )}
    </>
  );
}
