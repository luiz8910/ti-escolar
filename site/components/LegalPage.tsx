import type { ReactNode } from "react";
import { Container } from "@/components/ui";
import { ATUALIZADO_EM } from "@/lib/empresa";

/**
 * Casca das páginas legais (privacidade e termos).
 *
 * A tipografia é definida aqui com seletores de filho para não exigir o plugin
 * `@tailwindcss/typography` — o pacote tem só as dependências do painel.
 */
export function LegalPage({
  title,
  intro,
  children,
}: {
  title: string;
  intro: string;
  children: ReactNode;
}) {
  return (
    <>
      <div className="border-b border-n-200 bg-n-50">
        <Container>
          <div className="max-w-3xl py-14 sm:py-16">
            <h1 className="text-balance text-3xl font-extrabold tracking-tight text-n-900 sm:text-4xl">
              {title}
            </h1>
            <p className="mt-4 text-base leading-relaxed text-n-600">{intro}</p>
            <p className="mt-4 text-sm text-n-500">Última atualização: {ATUALIZADO_EM}.</p>
          </div>
        </Container>
      </div>

      <Container>
        <article
          className={[
            "max-w-3xl py-12 sm:py-16",
            "[&>h2]:mb-3 [&>h2]:mt-10 [&>h2]:text-xl [&>h2]:font-bold [&>h2]:tracking-tight [&>h2]:text-n-900",
            "[&>h2:first-child]:mt-0",
            "[&>h3]:mb-2 [&>h3]:mt-6 [&>h3]:text-base [&>h3]:font-bold [&>h3]:text-n-800",
            "[&>p]:mb-4 [&>p]:text-[0.95rem] [&>p]:leading-relaxed [&>p]:text-n-700",
            "[&>ul]:mb-4 [&>ul]:list-disc [&>ul]:space-y-2 [&>ul]:pl-5",
            "[&>ul>li]:text-[0.95rem] [&>ul>li]:leading-relaxed [&>ul>li]:text-n-700",
            "[&_strong]:font-semibold [&_strong]:text-n-900",
            "[&_a]:font-medium [&_a]:text-brand-600 [&_a]:underline-offset-4 hover:[&_a]:underline",
          ].join(" ")}
        >
          {children}
        </article>
      </Container>
    </>
  );
}
