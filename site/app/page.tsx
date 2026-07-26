import { ChatMock } from "@/components/ChatMock";
import {
  ArrowRightIcon,
  BellIcon,
  CapIcon,
  ChatBubbleIcon,
  CheckIcon,
  FileIcon,
  MailIcon,
  PhoneIcon,
  PrintIcon,
  SendIcon,
  ShieldIcon,
  SparkIcon,
  UsersIcon,
  WhatsAppIcon,
} from "@/components/icons";
import { Container, Cta, Eyebrow, FeatureCard, Section, SectionHeading } from "@/components/ui";
import { EMPRESA, PENDENTE, enderecoCompleto } from "@/lib/empresa";

/** Dados estruturados: ajudam buscadores e revisores a identificar a empresa. */
function OrganizationJsonLd() {
  const endereco = enderecoCompleto();
  const dados: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: EMPRESA.nome,
    legalName: EMPRESA.razaoSocial,
    url: EMPRESA.site,
    email: EMPRESA.email,
    description:
      "Plataforma de comunicação escolar pelo WhatsApp para escolas e secretarias.",
  };
  if (EMPRESA.cnpj !== PENDENTE) dados.taxID = EMPRESA.cnpj;
  if (EMPRESA.telefone !== PENDENTE) dados.telephone = EMPRESA.telefone;
  if (endereco) dados.address = endereco;

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(dados) }}
    />
  );
}

const DORES = [
  {
    titulo: "O WhatsApp da secretaria não para",
    texto:
      "As mesmas perguntas chegam o dia inteiro — horário, uniforme, documentos, calendário — e cada uma tira alguém de outra tarefa.",
  },
  {
    titulo: "Aviso importante que ninguém viu",
    texto:
      "Bilhete na mochila se perde, grupo de pais vira conversa paralela e não há como saber quem realmente recebeu o recado.",
  },
  {
    titulo: "Professor usando o número pessoal",
    texto:
      "Pedido de impressão, falta, recado para a família: tudo passa pelo celular particular do professor, sem registro nenhum.",
  },
];

const FUNCIONALIDADES = [
  {
    icon: <ChatBubbleIcon size={22} />,
    titulo: "Atendimento automático às famílias",
    texto:
      "O assistente responde dúvidas sobre procedimentos e avisos da escola a partir dos documentos que a própria secretaria cadastra — sempre citando a fonte da resposta.",
  },
  {
    icon: <FileIcon size={22} />,
    titulo: "Envio de documentos",
    texto:
      "Declarações, boletins, calendários e circulares chegam ao responsável direto na conversa, sem depender de alguém procurar o arquivo.",
  },
  {
    icon: <SendIcon size={22} />,
    titulo: "Avisos para turmas inteiras",
    texto:
      "Comunicados vão para grupos e turmas específicas, com controle de cota diária e acompanhamento de entrega por responsável.",
  },
  {
    icon: <UsersIcon size={22} />,
    titulo: "Cadastro escolar organizado",
    texto:
      "Alunos, responsáveis, turmas e professores em um só lugar — com importação em massa de planilhas e alerta de aluno sem contato cadastrado.",
  },
  {
    icon: <PrintIcon size={22} />,
    titulo: "Rotina interna da escola",
    texto:
      "Fila de impressão com cota por professor, mural com confirmação de leitura, canal do professor para a secretaria e aviso de falta com chamada de eventual.",
  },
  {
    icon: <CapIcon size={22} />,
    titulo: "Matrícula e ficha digital",
    texto:
      "Ficha de matrícula digitalizada com leitura assistida por IA e matrícula iniciada pelo próprio responsável, pelo WhatsApp.",
  },
];

const PASSOS = [
  {
    titulo: "A escola cadastra o que já tem",
    texto:
      "Procedimentos, circulares, respostas prontas da secretaria e a lista de alunos e responsáveis. Nada precisa ser reescrito: dá para subir planilha e documento.",
  },
  {
    titulo: "As famílias conversam pelo WhatsApp",
    texto:
      "O responsável manda a dúvida no número da escola e recebe a resposta na hora, com a fonte citada, ou o documento que pediu.",
  },
  {
    titulo: "A secretaria acompanha pelo painel",
    texto:
      "Todo o histórico de conversas, disparos e ações fica registrado — dá para ver quem recebeu, quem leu e o que o assistente respondeu.",
  },
];

const GARANTIAS = [
  "Cada escola é um ambiente isolado: dados de uma escola nunca aparecem para outra.",
  "Acesso ao painel por login individual, com perfis distintos para secretaria e professores.",
  "Histórico completo de conversas e de ações, para consulta e prestação de contas.",
  "Exportação de conversa em formato documental, quando a escola precisa anexar a um processo.",
  "Envio apenas pelos canais oficiais da plataforma WhatsApp Business, respeitando seus limites.",
];

export default function HomePage() {
  const endereco = enderecoCompleto();

  return (
    <>
      <OrganizationJsonLd />

      {/* ---------------------------------------------------------------- Hero */}
      <section className="relative overflow-hidden border-b border-n-200 bg-surface">
        <div className="hero-grid pointer-events-none absolute inset-0" aria-hidden />
        <Container className="relative">
          <div className="grid items-center gap-12 py-16 sm:py-20 lg:grid-cols-[1fr_auto] lg:gap-16 lg:py-24">
            <div className="max-w-xl">
              <span className="mb-5 inline-flex items-center gap-2 rounded-md bg-success-soft px-3 py-1.5 text-xs font-bold text-success">
                <WhatsAppIcon size={14} />
                No canal que as famílias já usam
              </span>

              <h1 className="text-balance text-3xl font-extrabold leading-[1.15] tracking-tight text-n-900 sm:text-4xl lg:text-[2.75rem]">
                A escola e as famílias, conectadas pelo WhatsApp.
              </h1>

              <p className="mt-5 text-base leading-relaxed text-n-600 sm:text-lg">
                O {EMPRESA.nome} responde as dúvidas dos responsáveis, envia documentos e
                avisos, e organiza a rotina entre secretaria e professores — sem instalar
                aplicativo nenhum e sem sobrecarregar quem atende.
              </p>

              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Cta href="/#contato" size="lg">
                  Falar com a gente
                  <ArrowRightIcon size={18} />
                </Cta>
                <Cta href="/#funcionalidades" variant="secondary" size="lg">
                  Ver o que faz
                </Cta>
              </div>

              <p className="mt-6 text-sm text-n-500">
                Feito para escolas públicas e privadas de educação básica.
              </p>
            </div>

            <div className="flex justify-center lg:justify-end">
              <ChatMock />
            </div>
          </div>
        </Container>
      </section>

      {/* --------------------------------------------------------------- Dores */}
      <Section tone="muted">
        <SectionHeading
          eyebrow="O problema"
          title="A comunicação da escola virou um segundo expediente"
          description="Quem trabalha na secretaria conhece a cena: o telefone tocando, o WhatsApp lotado e o aviso que, mesmo assim, não chegou em todo mundo."
        />

        <div className="mt-12 grid gap-6 md:grid-cols-3">
          {DORES.map((d) => (
            <div key={d.titulo} className="rounded-lg border border-n-200 bg-surface p-6">
              <h3 className="mb-2 text-base font-bold text-n-900">{d.titulo}</h3>
              <p className="text-sm leading-relaxed text-n-600">{d.texto}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* ------------------------------------------------------- Funcionalidades */}
      <Section id="funcionalidades">
        <SectionHeading
          eyebrow="Funcionalidades"
          title="Tudo o que a escola precisa responder, num canal só"
          description="Do atendimento ao responsável até a rotina interna entre secretaria e professores."
        />

        <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {FUNCIONALIDADES.map((f) => (
            <FeatureCard key={f.titulo} icon={f.icon} title={f.titulo}>
              {f.texto}
            </FeatureCard>
          ))}
        </div>
      </Section>

      {/* ------------------------------------------------------- Como funciona */}
      <Section id="como-funciona" tone="muted">
        <SectionHeading
          eyebrow="Como funciona"
          title="Três passos, sem projeto de TI"
          description="A escola não troca de sistema nem instala nada — o canal continua sendo o WhatsApp."
        />

        <ol className="mt-12 grid gap-6 md:grid-cols-3">
          {PASSOS.map((p, i) => (
            <li key={p.titulo} className="rounded-lg border border-n-200 bg-surface p-6">
              <span className="mb-4 flex h-9 w-9 items-center justify-center rounded-full bg-brand-600 text-sm font-extrabold text-white">
                {i + 1}
              </span>
              <h3 className="mb-2 text-base font-bold text-n-900">{p.titulo}</h3>
              <p className="text-sm leading-relaxed text-n-600">{p.texto}</p>
            </li>
          ))}
        </ol>
      </Section>

      {/* ----------------------------------------------------------- Segurança */}
      <Section id="seguranca">
        <div className="grid items-start gap-12 lg:grid-cols-2 lg:gap-16">
          <div>
            <Eyebrow>Segurança e privacidade</Eyebrow>
            <h2 className="text-balance text-2xl font-extrabold tracking-tight text-n-900 sm:text-3xl">
              Dado de aluno é dado sensível — e é tratado como tal
            </h2>
            <p className="mt-4 text-base leading-relaxed text-n-600">
              A plataforma lida com informações de crianças e adolescentes. O tratamento
              segue a Lei Geral de Proteção de Dados (Lei nº 13.709/2018), com a escola
              como controladora dos dados e o {EMPRESA.nome} como operador.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Cta href="/privacidade/" variant="secondary">
                <ShieldIcon size={17} />
                Política de Privacidade
              </Cta>
              <Cta href="/termos/" variant="ghost">
                Termos de Uso
              </Cta>
            </div>
          </div>

          <ul className="space-y-4">
            {GARANTIAS.map((g) => (
              <li key={g} className="flex gap-3">
                <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-success-soft text-success">
                  <CheckIcon size={13} />
                </span>
                <span className="text-sm leading-relaxed text-n-700">{g}</span>
              </li>
            ))}
          </ul>
        </div>
      </Section>

      {/* ------------------------------------------------------------- Contato */}
      <Section id="contato" tone="brand">
        <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
          <div>
            <SectionHeading
              eyebrow="Contato"
              title="Vamos conversar sobre a sua escola"
              description="Conte como a comunicação funciona hoje e mostramos como ficaria com o TI-Escolar."
              align="left"
              invert
            />
          </div>

          <div className="rounded-lg bg-white/10 p-6 backdrop-blur-sm sm:p-8">
            <ul className="space-y-4 text-sm">
              <li className="flex items-start gap-3">
                <span className="mt-0.5 flex h-9 w-9 flex-none items-center justify-center rounded-md bg-white/15 text-white">
                  <MailIcon size={18} />
                </span>
                <span>
                  <span className="block text-xs font-semibold uppercase tracking-wider text-brand-200">
                    E-mail
                  </span>
                  <a
                    className="font-semibold text-white underline-offset-4 hover:underline"
                    href={`mailto:${EMPRESA.email}`}
                  >
                    {EMPRESA.email}
                  </a>
                </span>
              </li>

              {EMPRESA.telefone !== PENDENTE && (
                <li className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-9 w-9 flex-none items-center justify-center rounded-md bg-white/15 text-white">
                    <PhoneIcon size={18} />
                  </span>
                  <span>
                    <span className="block text-xs font-semibold uppercase tracking-wider text-brand-200">
                      Telefone
                    </span>
                    <span className="font-semibold text-white">{EMPRESA.telefone}</span>
                  </span>
                </li>
              )}

              {endereco && (
                <li className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-9 w-9 flex-none items-center justify-center rounded-md bg-white/15 text-white">
                    <BellIcon size={18} />
                  </span>
                  <span>
                    <span className="block text-xs font-semibold uppercase tracking-wider text-brand-200">
                      Endereço
                    </span>
                    <span className="text-brand-100">{endereco}</span>
                  </span>
                </li>
              )}
            </ul>

            <div className="mt-7 border-t border-white/15 pt-6">
              <p className="mb-4 flex items-center gap-2 text-sm text-brand-100">
                <SparkIcon size={16} />
                Já é cliente?
              </p>
              <Cta href={EMPRESA.painelUrl} variant="onDark" external>
                Entrar no painel
                <ArrowRightIcon size={17} />
              </Cta>
            </div>
          </div>
        </div>
      </Section>
    </>
  );
}
