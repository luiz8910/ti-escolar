"use client";

import { useEffect, useState } from "react";
import { Container, Cta } from "@/components/ui";
import { Logo } from "@/components/Logo";
import { CloseIcon, MenuIcon } from "@/components/icons";
import { EMPRESA } from "@/lib/empresa";

const LINKS = [
  { href: "/#funcionalidades", label: "Funcionalidades" },
  { href: "/#como-funciona", label: "Como funciona" },
  { href: "/#seguranca", label: "Segurança" },
  { href: "/#contato", label: "Contato" },
];

export function Header() {
  const [aberto, setAberto] = useState(false);

  // Trava o scroll do corpo enquanto o menu mobile está aberto.
  useEffect(() => {
    if (!aberto) return;
    const anterior = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = anterior;
    };
  }, [aberto]);

  // Esc fecha o menu.
  useEffect(() => {
    if (!aberto) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAberto(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [aberto]);

  return (
    <header className="sticky top-0 z-40 border-b border-n-200/80 bg-surface/90 backdrop-blur">
      <Container>
        <div className="flex h-16 items-center justify-between gap-4">
          <a href="/" aria-label={`${EMPRESA.nome} — página inicial`}>
            <Logo />
          </a>

          <nav aria-label="Navegação principal" className="hidden items-center gap-1 lg:flex">
            {LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className="rounded-sm px-3 py-2 text-sm font-semibold text-n-600 transition-colors hover:text-brand-600"
              >
                {l.label}
              </a>
            ))}
          </nav>

          <div className="hidden items-center gap-3 lg:flex">
            <Cta href={EMPRESA.painelUrl} variant="secondary" external>
              Entrar no painel
            </Cta>
            <Cta href="/#contato">Falar com a gente</Cta>
          </div>

          <button
            type="button"
            onClick={() => setAberto((v) => !v)}
            aria-label={aberto ? "Fechar menu" : "Abrir menu"}
            aria-expanded={aberto}
            className="-mr-1 flex h-10 w-10 items-center justify-center rounded-md text-n-700 hover:bg-n-100 lg:hidden"
          >
            {aberto ? <CloseIcon size={22} /> : <MenuIcon size={22} />}
          </button>
        </div>
      </Container>

      {aberto && (
        <div className="border-t border-n-200 bg-surface lg:hidden">
          <Container>
            <nav aria-label="Navegação principal" className="flex flex-col gap-1 py-4">
              {LINKS.map((l) => (
                <a
                  key={l.href}
                  href={l.href}
                  onClick={() => setAberto(false)}
                  className="rounded-sm px-2 py-2.5 text-[0.95rem] font-semibold text-n-700 hover:bg-n-50 hover:text-brand-600"
                >
                  {l.label}
                </a>
              ))}
              <div className="mt-3 flex flex-col gap-2">
                <Cta href={EMPRESA.painelUrl} variant="secondary" external>
                  Entrar no painel
                </Cta>
                <Cta href="/#contato">Falar com a gente</Cta>
              </div>
            </nav>
          </Container>
        </div>
      )}
    </header>
  );
}
