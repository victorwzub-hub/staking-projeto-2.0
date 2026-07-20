import Link from "next/link";
import { AuthShell } from "@/components/auth/auth-shell";
export default function UnexpectedErrorPage() {
  return (
    <AuthShell
      title="Erro inesperado"
      description="A solicitação não pôde ser concluída. Tente novamente e use o correlation ID ao acionar o suporte."
    >
      <Link className="button" href="/app">
        Voltar
      </Link>
    </AuthShell>
  );
}
