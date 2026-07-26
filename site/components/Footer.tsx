import { Container } from "@/components/ui";
import { Logo } from "@/components/Logo";
import { MailIcon, PhoneIcon } from "@/components/icons";
import { ATUALIZADO_EM, EMPRESA, PENDENTE, enderecoCompleto } from "@/lib/empresa";

/**
 * Rodapé institucional.
 *
 * Além da navegação, este bloco existe para expor **razão social, CNPJ, endereço
 * e telefone** de forma pública e legível — é exatamente o que o revisor da Meta
 * procura ao validar a verificação da empresa, e o que a LGPD espera de um
 * controlador de dados. Não remova esses campos.
 */
export function Footer() {
  const endereco = enderecoCompleto();

  return (
    <footer className="border-t border-n-200 bg-n-50">
      <Container>
        <div className="grid gap-10 py-12 sm:grid-cols-2 lg:grid-cols-4 lg:py-14">
          <div className="lg:col-span-2">
            <Logo />
            <p className="mt-4 max-w-sm text-sm leading-relaxed text-n-600">
              Plataforma de comunicação escolar pelo WhatsApp: atendimento automático às
              famílias, envio de avisos e documentos, e organização da rotina interna da
              secretaria.
            </p>
          </div>

          <nav aria-label="Produto">
            <h2 className="mb-3 text-xs font-bold uppercase tracking-[0.14em] text-n-500">
              Produto
            </h2>
            <ul className="space-y-2.5 text-sm">
              <li>
                <a className="text-n-600 hover:text-brand-600" href="/#funcionalidades">
                  Funcionalidades
                </a>
              </li>
              <li>
                <a className="text-n-600 hover:text-brand-600" href="/#como-funciona">
                  Como funciona
                </a>
              </li>
              <li>
                <a className="text-n-600 hover:text-brand-600" href="/#seguranca">
                  Segurança e LGPD
                </a>
              </li>
              <li>
                <a
                  className="text-n-600 hover:text-brand-600"
                  href={EMPRESA.painelUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Entrar no painel
                </a>
              </li>
            </ul>
          </nav>

          <nav aria-label="Legal e contato">
            <h2 className="mb-3 text-xs font-bold uppercase tracking-[0.14em] text-n-500">
              Legal
            </h2>
            <ul className="space-y-2.5 text-sm">
              <li>
                <a className="text-n-600 hover:text-brand-600" href="/privacidade/">
                  Política de Privacidade
                </a>
              </li>
              <li>
                <a className="text-n-600 hover:text-brand-600" href="/termos/">
                  Termos de Uso
                </a>
              </li>
              <li>
                <a
                  className="inline-flex items-center gap-1.5 text-n-600 hover:text-brand-600"
                  href={`mailto:${EMPRESA.email}`}
                >
                  <MailIcon size={15} />
                  {EMPRESA.email}
                </a>
              </li>
              {EMPRESA.telefone !== PENDENTE && (
                <li>
                  <span className="inline-flex items-center gap-1.5 text-n-600">
                    <PhoneIcon size={15} />
                    {EMPRESA.telefone}
                  </span>
                </li>
              )}
            </ul>
          </nav>
        </div>

        {/* ------------------------------------------------------------------
            Identificação legal do controlador. Bloco exigido pela verificação
            da Meta e pela LGPD — mantenha visível e sem JavaScript.
           ------------------------------------------------------------------ */}
        <div className="border-t border-n-200 py-8">
          <address className="not-italic text-sm leading-relaxed text-n-600">
            <span className="font-semibold text-n-800">{EMPRESA.razaoSocial}</span>
            {EMPRESA.cnpj !== PENDENTE && (
              <>
                {" — "}
                <span>
                  CNPJ <span className="font-mono">{EMPRESA.cnpj}</span>
                </span>
              </>
            )}
            {endereco && (
              <>
                <br />
                {endereco}
              </>
            )}
          </address>

          <div className="mt-5 flex flex-col gap-2 text-xs text-n-500 sm:flex-row sm:items-center sm:justify-between">
            <p>
              © {new Date().getFullYear()} {EMPRESA.razaoSocial}. Todos os direitos
              reservados.
            </p>
            <p>Atualizado em {ATUALIZADO_EM}.</p>
          </div>

          <p className="mt-4 text-xs leading-relaxed text-n-400">
            WhatsApp é uma marca registrada da Meta Platforms, Inc. O {EMPRESA.nome} não
            possui vínculo societário com a Meta e utiliza a plataforma como canal de
            comunicação autorizado.
          </p>
        </div>
      </Container>
    </footer>
  );
}
