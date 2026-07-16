import Link from "next/link";
import { AuthShell } from "@/components/auth/auth-shell";
export default function SessionExpiredPage() {
  return (
    <AuthShell
      title="Sessão expirada"
      description="Entre novamente para estabelecer uma nova sessão segura."
    >
      <Link className="button" href="/login">
        Entrar novamente
      </Link>
    </AuthShell>
  );
}
