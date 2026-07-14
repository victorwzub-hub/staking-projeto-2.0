export default function Loading() {
  return (
    <section className="container hero" aria-busy="true" aria-live="polite">
      <div className="skeleton skeleton-small" />
      <div className="skeleton skeleton-title" />
      <div className="skeleton skeleton-copy" />
      <span className="sr-only">Carregando conteúdo</span>
    </section>
  );
}
