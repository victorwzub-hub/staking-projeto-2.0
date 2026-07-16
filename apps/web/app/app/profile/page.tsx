"use client";

import type { Profile } from "@pharma/contracts";
import { FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { FormField } from "@/components/ui/form-field";
import { LoadingState, PageHeader } from "@/components/ui/page-state";
import { useAuth } from "@/lib/auth/auth-context";
import { useSubmit } from "@/lib/forms/use-submit";
import { apiJson } from "@/lib/http/client";
import { useApi } from "@/lib/http/use-api";

export default function ProfilePage() {
  const profile = useApi<Profile>("me/profile");
  const submit = useSubmit<Profile>();
  const auth = useAuth();
  if (profile.status === "loading") return <LoadingState label="Carregando perfil" />;
  if (profile.status === "error")
    return (
      <Alert tone="danger" title="Perfil indisponível">
        {profile.error.message}
      </Alert>
    );
  const currentProfile = profile.data;
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const result = await submit.run(() =>
      apiJson("me/profile", "PATCH", {
        display_name: form.get("display_name"),
        locale: form.get("locale"),
        timezone: form.get("timezone"),
        expected_version: currentProfile.version,
      }),
    );
    if (result) {
      await profile.reload();
      await auth.refresh();
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="Conta"
        title="Perfil"
        description="Dados pessoais mínimos e preferências operacionais."
      />
      <form className="content-card form-grid" onSubmit={handleSubmit}>
        {submit.error ? (
          <div className="form-span">
            <Alert tone="danger" title="Falha ao atualizar">
              {submit.error.message}
            </Alert>
          </div>
        ) : null}
        {submit.data ? (
          <div className="form-span">
            <Alert tone="success" title="Perfil atualizado">
              As alterações foram registradas em auditoria.
            </Alert>
          </div>
        ) : null}
        <FormField
          label="Nome de exibição"
          name="display_name"
          defaultValue={currentProfile.display_name}
          required
        />
        <FormField label="Locale" name="locale" defaultValue={currentProfile.locale} required />
        <FormField
          label="Fuso horário"
          name="timezone"
          defaultValue={currentProfile.timezone}
          required
        />
        <div className="form-span">
          <button className="button" disabled={submit.pending}>
            {submit.pending ? "Salvando…" : "Salvar perfil"}
          </button>
        </div>
      </form>
    </>
  );
}
