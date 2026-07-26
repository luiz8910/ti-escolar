import { Container, Cta } from "@/components/ui";

export default function NotFound() {
  return (
    <Container>
      <div className="mx-auto max-w-lg py-24 text-center sm:py-32">
        <p className="text-sm font-bold uppercase tracking-[0.14em] text-brand-600">
          Erro 404
        </p>
        <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-n-900">
          Página não encontrada
        </h1>
        <p className="mt-4 text-base leading-relaxed text-n-600">
          O endereço que você acessou não existe ou foi movido.
        </p>
        <div className="mt-8 flex justify-center">
          <Cta href="/">Voltar para o início</Cta>
        </div>
      </div>
    </Container>
  );
}
