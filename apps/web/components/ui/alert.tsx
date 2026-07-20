export function Alert({
  children,
  tone = "error",
  title,
}: {
  children: React.ReactNode;
  tone?: "error" | "danger" | "success" | "info" | "warning";
  title?: string;
}) {
  const normalizedTone = tone === "danger" ? "error" : tone;
  return (
    <div
      className={`alert alert-${normalizedTone}`}
      role={normalizedTone === "error" ? "alert" : "status"}
    >
      {title ? <strong>{title}</strong> : null}
      <div>{children}</div>
    </div>
  );
}
