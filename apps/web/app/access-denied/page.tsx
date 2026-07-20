import Link from "next/link";
import { AuthShell } from "@/components/auth/auth-shell";
export default function AccessDeniedPage() {
  return (
    <AuthShell
      title="Acesso negado"
      description="Sua sessão é válida, mas não possui a permissão necessária para este recurso."
    >
      <Link className="button" href="/app">
        Voltar à aplicação
      </Link>
    </AuthShell>
  );
}
