import Link from "next/link";

export default function NotFound() {
  return (
    <section className="container hero">
      <div className="eyebrow">404</div>
      <h1>Página não encontrada.</h1>
      <p className="lead">O endereço informado não existe nesta versão da plataforma.</p>
      <Link className="button" href="/">
        Voltar ao início
      </Link>
    </section>
  );
}
