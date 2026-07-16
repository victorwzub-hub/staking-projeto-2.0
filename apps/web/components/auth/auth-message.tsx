import { Alert } from "@/components/ui/alert";

export function AuthMessage({ error, success }: { error?: Error | null; success?: string | null }) {
  if (error)
    return (
      <Alert tone="danger" title="Não foi possível concluir">
        {error.message}
      </Alert>
    );
  if (success)
    return (
      <Alert tone="success" title="Solicitação concluída">
        {success}
      </Alert>
    );
  return null;
}
