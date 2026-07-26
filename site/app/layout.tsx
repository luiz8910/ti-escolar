import type { Metadata } from "next";
import { JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { EMPRESA } from "@/lib/empresa";

/**
 * Fontes auto-hospedadas pelo next/font: baixadas no build e servidas junto do
 * site. A página não faz nenhuma requisição a domínio externo em runtime — o que
 * também evita que um bloqueio de rede quebre a tipografia durante a análise da
 * verificação da Meta.
 */
const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-jakarta",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-jetbrains",
  display: "swap",
});

const DESCRICAO =
  "Plataforma de comunicação escolar pelo WhatsApp: atendimento automático às " +
  "famílias, envio de avisos e documentos, e organização da rotina da secretaria.";

export const metadata: Metadata = {
  metadataBase: new URL(EMPRESA.site),
  title: {
    default: `${EMPRESA.nome} — comunicação escolar pelo WhatsApp`,
    template: `%s · ${EMPRESA.nome}`,
  },
  description: DESCRICAO,
  applicationName: EMPRESA.nome,
  keywords: [
    "comunicação escolar",
    "WhatsApp para escolas",
    "secretaria escolar",
    "avisos para pais",
    "gestão escolar",
  ],
  openGraph: {
    type: "website",
    locale: "pt_BR",
    url: EMPRESA.site,
    siteName: EMPRESA.nome,
    title: `${EMPRESA.nome} — comunicação escolar pelo WhatsApp`,
    description: DESCRICAO,
  },
  robots: { index: true, follow: true },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className={`${jakarta.variable} ${jetbrains.variable}`}>
      <body className="flex min-h-full flex-col">
        <a
          href="#conteudo"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-brand-600 focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-white"
        >
          Pular para o conteúdo
        </a>
        <Header />
        <main id="conteudo" className="flex-1">
          {children}
        </main>
        <Footer />
      </body>
    </html>
  );
}
