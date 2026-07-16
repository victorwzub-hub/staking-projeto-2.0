import Link from "next/link";

export function AuthShell({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="auth-title">
        <Link className="brand" href="/">
          Pharma Intelligence
        </Link>
        <div className="auth-heading">
          <h1 id="auth-title">{title}</h1>
          <p>{description}</p>
        </div>
        {children}
        {footer ? <div className="auth-footer">{footer}</div> : null}
      </section>
    </main>
  );
}
