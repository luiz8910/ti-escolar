"use client";

/**
 * Escolas — a tela de trabalho do super admin (§6d, §6e).
 *
 * Duas decisões de desenho guiam o arquivo:
 *
 * - **A lista é para achar e agir, não para ler tudo.** Os filtros particionam as escolas
 *   pelo que exige atenção (vencendo, bloqueadas), e as ações que mudam o estado da
 *   escola ficam atrás do menu "⋯" — com uma exceção: a escola bloqueada mostra
 *   "Desbloquear" na linha, porque é a única coisa que alguém vem fazer com ela.
 * - **Cadastro e edição são o mesmo painel lateral.** Três blocos (identificação,
 *   expediente, WhatsApp) não cabiam num modal sem esconder o "Salvar"; e o WhatsApp é
 *   opcional de propósito — o onboarding do número tem tela própria (`/whatsapp`),
 *   porque cada passo dele é uma chamada à Meta com efeito real.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  atualizarEscola,
  bloquearEscola,
  cancelarEscola,
  ContaWhatsApp,
  criarEscola,
  definirLicenca,
  desbloquearEscola,
  Escola,
  getSessao,
  Licenca,
  listarContasWhatsApp,
  listarEscolas,
  logout,
  notificarVencimento,
  reativarEscola,
  removerEscola,
  setEscolaEmFoco,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/Button";
import { Input, Field, Select, Textarea } from "@/components/ui/form";
import { CampoData } from "@/components/ui/campos";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { Drawer } from "@/components/ui/Drawer";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/components/ui/cn";
import {
  CamposExpediente,
  EXPEDIENTE_PADRAO,
  paraEntrada,
  resumoDias,
  type EstadoExpediente,
} from "@/components/admin/CamposExpediente";
import {
  PlusIcon,
  ExternalIcon,
  SearchIcon,
  CalendarIcon,
  WhatsAppIcon,
  DotsIcon,
  PencilIcon,
  CardIcon,
  LockIcon,
  UnlockIcon,
  XCircleIcon,
  TrashIcon,
  ChatBubbleIcon,
  UsersIcon,
  BellIcon,
} from "@/components/ui/icons";

/* ---------- Classificação e formatação ------------------------------------ */

type Categoria = "ativas" | "vencendo" | "bloqueadas" | "canceladas";
type Filtro = "todas" | Categoria;

/** Janela em que uma licença conta como "vencendo" — a mesma do badge antigo. */
const DIAS_AVISO_VENCIMENTO = 30;

/**
 * Cada escola cai em **uma** categoria, para os contadores dos filtros somarem o total.
 * Bloqueio e cancelamento vencem o prazo: uma escola bloqueada e vencida está, antes de
 * tudo, bloqueada. Licença já expirada conta como "vencendo" — é o mesmo pedido de ação.
 */
function categoria(l: Licenca): Categoria {
  if (l.status === "cancelado") return "canceladas";
  if (l.status === "bloqueado") return "bloqueadas";
  if (
    l.licenca_expirada ||
    (l.dias_para_expirar !== null && l.dias_para_expirar <= DIAS_AVISO_VENCIMENTO)
  ) {
    return "vencendo";
  }
  return "ativas";
}

/** Espelho do `slugify` do back-end — só para a prévia; quem decide é a API. */
function slugify(texto: string): string {
  return texto
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function semAcento(texto: string): string {
  return texto.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/** "+5515997536978" → "+55 15 99753-6978". Fora do Brasil, devolve o E.164 como veio. */
function formatarTelefone(e164: string): string {
  const d = e164.replace(/\D/g, "");
  if (d.startsWith("55") && (d.length === 12 || d.length === 13)) {
    const numero = d.slice(4);
    return `+55 ${d.slice(2, 4)} ${numero.slice(0, -4)}-${numero.slice(-4)}`;
  }
  return e164;
}

function formatarData(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    timeZone: "UTC",
  });
}

function sigla(nome: string) {
  return nome
    .split(" ")
    .filter((p) => p.length > 2 || /^[A-Z]/.test(p))
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

/** Cor do avatar derivada do id: estável entre recargas e diferente entre vizinhas. */
const CORES_AVATAR = ["#2457D6", "#7A4FD6", "#0F766E", "#C2410C", "#BE185D", "#0369A1"];
function corAvatar(id: string): string {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return CORES_AVATAR[h % CORES_AVATAR.length];
}

/* ---------- Página -------------------------------------------------------- */

type Acao =
  | { tipo: "bloquear" | "cancelar" | "licenca" | "excluir"; escola: Escola }
  | null;

type Painel = { modo: "nova" } | { modo: "editar"; escola: Escola } | null;

export default function EscolasPage() {
  const router = useRouter();
  const toast = useToast();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [escolas, setEscolas] = useState<Escola[]>([]);
  const [contas, setContas] = useState<ContaWhatsApp[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [busca, setBusca] = useState("");
  const [painel, setPainel] = useState<Painel>(null);
  const [acao, setAcao] = useState<Acao>(null);

  const recarregar = useCallback(async () => {
    const [lista, contasWhats] = await Promise.all([listarEscolas(), listarContasWhatsApp()]);
    setEscolas(lista);
    setContas(contasWhats);
  }, []);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    if (s.usuario.papel !== "super_admin") {
      router.replace("/admin");
      return;
    }
    setUsuario(s.usuario);
    recarregar()
      .catch(() => toast({ tone: "danger", title: "Falha ao carregar escolas." }))
      .finally(() => setCarregando(false));
  }, [router, recarregar, toast]);

  const contagem = useMemo(() => {
    const c: Record<Filtro, number> = {
      todas: escolas.length,
      ativas: 0,
      vencendo: 0,
      bloqueadas: 0,
      canceladas: 0,
    };
    for (const e of escolas) c[categoria(e.licenca)] += 1;
    return c;
  }, [escolas]);

  const visiveis = useMemo(() => {
    const termo = semAcento(busca.trim());
    const digitos = busca.replace(/\D/g, "");
    return escolas.filter((e) => {
      if (filtro !== "todas" && categoria(e.licenca) !== filtro) return false;
      if (!termo) return true;
      if (semAcento(e.nome).includes(termo) || e.slug.includes(termo)) return true;
      // Telefone se busca pelos dígitos: "15 99753" tem de achar "+5515997536978".
      return (
        digitos.length >= 3 &&
        [e.telefone_contato, e.whatsapp_numero].some((t) => t.replace(/\D/g, "").includes(digitos))
      );
    });
  }, [escolas, filtro, busca]);

  const nomeDaConta = useCallback(
    (id: string | null) => (id ? (contas.find((c) => c.id === id)?.nome ?? "conta removida") : null),
    [contas],
  );

  async function executar(fn: () => Promise<unknown>, sucesso: string, falha: string) {
    try {
      await fn();
      await recarregar();
      toast({ tone: "success", title: sucesso });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : falha });
    }
  }

  const acoesDaLinha: AcoesDaLinha = {
    editar: (escola) => setPainel({ modo: "editar", escola }),
    licenca: (escola) => setAcao({ tipo: "licenca", escola }),
    bloquear: (escola) => setAcao({ tipo: "bloquear", escola }),
    cancelar: (escola) => setAcao({ tipo: "cancelar", escola }),
    excluir: (escola) => setAcao({ tipo: "excluir", escola }),
    desbloquear: (escola) =>
      executar(() => desbloquearEscola(escola.id), "Escola desbloqueada.", "Falha ao desbloquear."),
    reativar: (escola) =>
      executar(() => reativarEscola(escola.id), "Escola reativada.", "Falha ao reativar."),
    conversas: (escola) => {
      // As conversas moram nas telas da escola em foco: escolher a escola é o atalho.
      setEscolaEmFoco({ tenantId: escola.id, nome: escola.nome });
      router.push("/admin/historico/conversas");
    },
  };

  function sair() {
    logout();
    router.replace("/admin/login");
  }

  if (!usuario) return null;

  const filtros: { valor: Filtro; rotulo: string }[] = [
    { valor: "todas", rotulo: "Todas" },
    { valor: "ativas", rotulo: "Ativas" },
    { valor: "vencendo", rotulo: "Vencendo" },
    { valor: "bloqueadas", rotulo: "Bloqueadas" },
    // Cancelada é exceção: o filtro só aparece quando há o que mostrar nele.
    ...(contagem.canceladas > 0 || filtro === "canceladas"
      ? [{ valor: "canceladas" as const, rotulo: "Canceladas" }]
      : []),
  ];

  return (
    <AppShell
      exigeEscola={false}
      title="Escolas"
      user={{ name: usuario.nome, role: "Super Admin" }}
      isSuperAdmin
      onLogout={sair}
    >
      <div className="flex flex-col gap-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h1 className="text-[26px] font-bold tracking-[-0.02em] text-n-900">
              Escolas
              <span className="ml-2 text-[15px] font-medium tracking-normal text-n-500 min-[1440px]:hidden">
                · {escolas.length}
              </span>
            </h1>
            <p className="hidden text-sm text-n-500 sm:block">
              Gerencie as escolas, licenças e números de WhatsApp da plataforma.
            </p>
          </div>
          <div className="flex gap-2.5">
            <AvisarVencimentos />
            <Button leftIcon={<PlusIcon size={16} />} onClick={() => setPainel({ modo: "nova" })}>
              Nova escola
            </Button>
          </div>
        </div>

        <section className="rounded-[14px] border border-n-200 bg-white">
          <div className="flex flex-col-reverse gap-3 border-b border-n-100 px-5 py-4 min-[1440px]:flex-row min-[1440px]:items-center min-[1440px]:justify-between">
            <div
              role="tablist"
              aria-label="Filtrar escolas"
              className="flex w-fit max-w-full gap-1 overflow-x-auto rounded-[10px] bg-n-100 p-1"
            >
              {filtros.map((f) => {
                const ativo = filtro === f.valor;
                const destaque = f.valor === "vencendo" && contagem.vencendo > 0;
                return (
                  <button
                    key={f.valor}
                    type="button"
                    role="tab"
                    aria-selected={ativo}
                    onClick={() => setFiltro(f.valor)}
                    className={cn(
                      "flex h-8 flex-none items-center gap-2 rounded-[7px] px-3 text-[13px] transition-colors",
                      ativo
                        ? "bg-white font-semibold text-n-900 shadow-sm"
                        : "font-medium text-n-700 hover:text-n-900",
                    )}
                  >
                    {f.rotulo}
                    <span
                      className={cn(
                        "tabular-nums",
                        destaque
                          ? "rounded-full bg-accent-soft px-[7px] py-px text-[11px] font-bold text-[#8A4B00]"
                          : "text-xs font-medium text-n-500",
                      )}
                    >
                      {contagem[f.valor]}
                    </span>
                  </button>
                );
              })}
            </div>
            <label className="relative flex w-full items-center min-[1440px]:w-[360px]">
              <SearchIcon size={16} className="pointer-events-none absolute left-3 text-n-500" />
              <input
                type="search"
                aria-label="Buscar escolas"
                placeholder="Buscar por nome, slug ou telefone"
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                className="h-[38px] w-full rounded-[10px] border border-n-300 bg-white pl-9 pr-3 text-sm text-n-900 outline-none placeholder:text-n-400 focus:border-brand-500 focus:ring-[3px] focus:ring-brand-500/20"
              />
            </label>
          </div>

          {carregando ? (
            <p className="px-5 py-10 text-center text-sm text-n-400">Carregando…</p>
          ) : escolas.length === 0 ? (
            <div className="flex flex-col items-center gap-3 px-5 py-12 text-center">
              <p className="text-sm text-n-500">Nenhuma escola cadastrada ainda.</p>
              <Button size="sm" leftIcon={<PlusIcon size={15} />} onClick={() => setPainel({ modo: "nova" })}>
                Cadastrar a primeira
              </Button>
            </div>
          ) : visiveis.length === 0 ? (
            <p className="px-5 py-10 text-center text-sm text-n-500">
              Nenhuma escola encontrada
              {busca.trim() ? <> para &ldquo;{busca.trim()}&rdquo;</> : " neste filtro"}.
            </p>
          ) : (
            <>
              <TabelaEscolas escolas={visiveis} nomeDaConta={nomeDaConta} acoes={acoesDaLinha} />
              <CartoesEscolas escolas={visiveis} nomeDaConta={nomeDaConta} acoes={acoesDaLinha} />
            </>
          )}
        </section>
      </div>

      {painel && (
        <EscolaDrawer
          key={painel.modo === "editar" ? painel.escola.id : "nova"}
          escola={painel.modo === "editar" ? painel.escola : null}
          contas={contas}
          onClose={() => setPainel(null)}
          onSalva={recarregar}
        />
      )}

      {acao?.tipo === "bloquear" && (
        <BloquearModal escola={acao.escola} onClose={() => setAcao(null)} onMudou={recarregar} />
      )}
      {acao?.tipo === "cancelar" && (
        <CancelarModal escola={acao.escola} onClose={() => setAcao(null)} onMudou={recarregar} />
      )}
      {acao?.tipo === "licenca" && (
        <LicencaModal escola={acao.escola} onClose={() => setAcao(null)} onMudou={recarregar} />
      )}
      <ConfirmDialog
        open={acao?.tipo === "excluir"}
        onClose={() => setAcao(null)}
        onConfirm={() => {
          const alvo = acao?.escola;
          setAcao(null);
          if (alvo) {
            executar(() => removerEscola(alvo.id), "Escola excluída.", "Falha ao excluir.");
          }
        }}
        title="Excluir escola"
        message={`Excluir "${acao?.escola.nome ?? ""}" e TODOS os seus dados (conversas, contatos, mensagens)? Esta ação é irreversível.`}
      />
    </AppShell>
  );
}

function AvisarVencimentos() {
  const toast = useToast();
  const [enviando, setEnviando] = useState(false);

  async function avisar() {
    setEnviando(true);
    try {
      const avisos = await notificarVencimento();
      toast({
        tone: "success",
        title: avisos.length
          ? `${avisos.length} escola(s) avisada(s) por e-mail.`
          : "Nenhuma licença anual perto do vencimento.",
      });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao avisar." });
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Button
      variant="secondary"
      loading={enviando}
      onClick={avisar}
      leftIcon={<CalendarIcon size={16} />}
      aria-label="Avisar vencimentos"
      title="Envia e-mail aos admins das escolas com licença anual perto de vencer"
    >
      <span className="hidden sm:inline">Avisar vencimentos</span>
      <span className="sm:hidden">Vencimentos</span>
    </Button>
  );
}

/* ---------- Lista: tabela (larga) e cartões (estreita) --------------------- */

interface AcoesDaLinha {
  editar: (e: Escola) => void;
  licenca: (e: Escola) => void;
  bloquear: (e: Escola) => void;
  cancelar: (e: Escola) => void;
  excluir: (e: Escola) => void;
  desbloquear: (e: Escola) => void;
  reativar: (e: Escola) => void;
  conversas: (e: Escola) => void;
}

interface PropsLista {
  escolas: Escola[];
  nomeDaConta: (id: string | null) => string | null;
  acoes: AcoesDaLinha;
}

// Mesmas colunas no cabeçalho e nas linhas — mudar num lugar só. Os três contadores
// dividem uma coluna ("Atividade"): com a sidebar do painel, três colunas numéricas
// espremiam justamente nome e WhatsApp, que são o que se lê.
const COLUNAS =
  "grid grid-cols-[minmax(0,1.7fr)_152px_124px_minmax(0,1.3fr)_104px_124px_172px] gap-3.5";

function TabelaEscolas({ escolas, nomeDaConta, acoes }: PropsLista) {
  return (
    <div className="hidden min-[1440px]:block" role="table" aria-label="Escolas">
      <div
        role="row"
        className={cn(
          COLUNAS,
          "border-b border-n-100 bg-n-50 px-5 py-2.5 text-[11.5px] font-semibold uppercase tracking-[0.04em] text-n-500",
        )}
      >
        <div role="columnheader">Escola</div>
        <div role="columnheader">Licença</div>
        <div role="columnheader">Contato</div>
        <div role="columnheader">WhatsApp</div>
        <div role="columnheader">Expediente</div>
        <div role="columnheader">Atividade</div>
        <div role="columnheader" className="text-right">Ações</div>
      </div>
      {escolas.map((e) => {
        const apagada = e.licenca.status !== "ativo";
        return (
          <div
            key={e.id}
            role="row"
            className={cn(
              COLUNAS,
              "items-center border-b border-n-100 px-5 py-4 last:border-b-0",
              apagada && "bg-n-50/60",
            )}
          >
            <div role="cell" className="min-w-0">
              <IdentidadeEscola escola={e} />
            </div>
            <div role="cell" className="flex flex-col items-start gap-1">
              <EstadoLicenca licenca={e.licenca} />
              <span className="whitespace-nowrap text-xs text-n-500">{detalheLicenca(e.licenca)}</span>
            </div>
            <div role="cell" className={cn("whitespace-nowrap text-[13px]", apagada ? "text-n-700" : "text-n-900")}>
              {e.telefone_contato ? formatarTelefone(e.telefone_contato) : "—"}
            </div>
            <div role="cell" className="min-w-0">
              <WhatsAppDaEscola escola={e} nomeDaConta={nomeDaConta} />
            </div>
            <div role="cell">
              <ExpedienteDaEscola escola={e} />
            </div>
            <div role="cell" className="flex items-center gap-3 text-[13px] tabular-nums text-n-500">
              <Contador rotulo="Conversas" valor={e.total_conversas} icone={<ChatBubbleIcon size={15} />} destaque />
              <Contador rotulo="Usuários do painel" valor={e.total_usuarios} icone={<UsersIcon size={15} />} />
              <Contador rotulo="Disparos" valor={e.total_broadcasts} icone={<BellIcon size={15} />} />
            </div>
            <div role="cell" className="flex justify-end gap-1.5">
              <AcoesPrincipais escola={e} acoes={acoes} />
              <MenuAcoes escola={e} acoes={acoes} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CartoesEscolas({ escolas, nomeDaConta, acoes }: PropsLista) {
  return (
    <div className="flex flex-col gap-3 bg-n-50 p-3 min-[1440px]:hidden">
      {escolas.map((e) => (
        <article
          key={e.id}
          className="flex flex-col gap-4 rounded-[14px] border border-n-200 bg-white px-5 py-[18px]"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <IdentidadeEscola escola={e} comLicenca />
            <div className="flex gap-1.5">
              <AcoesPrincipais escola={e} acoes={acoes} />
              <MenuAcoes escola={e} acoes={acoes} />
            </div>
          </div>
          <dl className="grid grid-cols-1 gap-4 border-t border-n-100 pt-3.5 sm:grid-cols-2 lg:grid-cols-4">
            <Detalhe rotulo="Contato">
              {e.telefone_contato ? formatarTelefone(e.telefone_contato) : "—"}
            </Detalhe>
            <Detalhe rotulo="WhatsApp da plataforma">
              <WhatsAppDaEscola escola={e} nomeDaConta={nomeDaConta} />
            </Detalhe>
            <Detalhe rotulo="Expediente">
              {e.expediente
                ? `${resumoDias(e.expediente.dias)} · ${e.expediente.inicio} – ${e.expediente.fim}`
                : "Não definido"}
            </Detalhe>
            <Detalhe rotulo="Atividade">
              {e.total_conversas} conversa{e.total_conversas === 1 ? "" : "s"} ·{" "}
              {e.total_usuarios} usuário{e.total_usuarios === 1 ? "" : "s"} ·{" "}
              {e.total_broadcasts} disparo{e.total_broadcasts === 1 ? "" : "s"}
            </Detalhe>
          </dl>
        </article>
      ))}
    </div>
  );
}

function Detalhe({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <dt className="text-xs font-semibold text-n-500">{rotulo}</dt>
      <dd className="text-[13px] text-n-900">{children}</dd>
    </div>
  );
}

function Contador({
  rotulo,
  valor,
  icone,
  destaque = false,
}: {
  rotulo: string;
  valor: number;
  icone: ReactNode;
  destaque?: boolean;
}) {
  return (
    <span
      title={`${rotulo}: ${valor}`}
      aria-label={`${rotulo}: ${valor}`}
      className={cn("flex items-center gap-1", destaque && valor > 0 && "font-semibold text-n-900")}
    >
      {icone}
      {valor}
    </span>
  );
}

function IdentidadeEscola({ escola, comLicenca = false }: { escola: Escola; comLicenca?: boolean }) {
  const apagada = escola.licenca.status !== "ativo";
  return (
    <div className="flex min-w-0 items-center gap-3">
      <div
        className={cn(
          "flex h-10 w-10 flex-none items-center justify-center rounded-[10px] text-sm font-bold",
          apagada ? "bg-n-300 text-n-700" : "text-white",
        )}
        style={apagada ? undefined : { backgroundColor: corAvatar(escola.id) }}
        aria-hidden
      >
        {sigla(escola.nome)}
      </div>
      <div className="flex min-w-0 flex-col gap-0.5">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <Link
            href={`/admin/escolas/detalhe?tenant=${escola.id}`}
            title={escola.nome}
            className={cn(
              "truncate text-[15px] font-semibold no-underline hover:text-brand-700 hover:underline",
              apagada ? "text-n-700" : "text-n-900",
            )}
          >
            {escola.nome}
          </Link>
          {comLicenca && <EstadoLicenca licenca={escola.licenca} comPlano />}
        </div>
        <span className="truncate font-mono text-xs text-n-500">{escola.slug}</span>
      </div>
    </div>
  );
}

function EstadoLicenca({ licenca, comPlano = false }: { licenca: Licenca; comPlano?: boolean }) {
  const plano = licenca.plano === "anual" ? "Anual" : "Mensal";
  const pilula = "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-[9px] py-[3px] text-xs font-semibold";
  const ponto = "h-1.5 w-1.5 rounded-full";

  if (licenca.status === "cancelado") {
    return (
      <span className={cn(pilula, "bg-n-100 text-n-600")} title={licenca.motivo_cancelamento}>
        <XCircleIcon size={11} />
        Cancelada
      </span>
    );
  }
  if (licenca.status === "bloqueado") {
    return (
      <span className={cn(pilula, "bg-danger-soft text-[#A32022]")} title={licenca.motivo_bloqueio}>
        <LockIcon size={11} strokeWidth={2.4} />
        Bloqueada
      </span>
    );
  }
  if (licenca.licenca_expirada) {
    return (
      <span className={cn(pilula, "bg-danger-soft text-[#A32022]")}>
        <span className={cn(ponto, "bg-danger")} />
        Licença expirada
      </span>
    );
  }
  const d = licenca.dias_para_expirar;
  if (d !== null && d <= DIAS_AVISO_VENCIMENTO) {
    return (
      <span className={cn(pilula, "bg-accent-soft text-[#8A4B00]")}>
        <span className={cn(ponto, "bg-accent")} />
        {d === 0 ? "Vence hoje" : `Vence em ${d} dia${d === 1 ? "" : "s"}`}
      </span>
    );
  }
  return (
    <span className={cn(pilula, "bg-success-soft text-[#146C43]")}>
      <span className={cn(ponto, "bg-success")} />
      Ativa{comPlano ? ` · ${plano}` : ""}
    </span>
  );
}

/** A segunda linha da coluna Licença: plano e a data que importa para o estado atual. */
function detalheLicenca(l: Licenca): string {
  const plano = l.plano === "anual" ? "Anual" : "Mensal";
  if (l.status === "cancelado" && l.cancelado_em) return `${plano} · desde ${formatarData(l.cancelado_em)}`;
  if (l.status === "bloqueado" && l.bloqueado_em) return `${plano} · desde ${formatarData(l.bloqueado_em)}`;
  if (l.licenca_expira_em) {
    return `${plano} · ${l.licenca_expirada ? "venceu" : "até"} ${formatarData(l.licenca_expira_em)}`;
  }
  return `${plano} · sem vencimento`;
}

function WhatsAppDaEscola({
  escola,
  nomeDaConta,
}: {
  escola: Escola;
  nomeDaConta: (id: string | null) => string | null;
}) {
  // Sem phone_number_id o inbound desta escola é descartado — para efeito de atendimento,
  // o número não existe, tenha ou não um E.164 anotado.
  if (!escola.meta_phone_number_id) {
    return (
      <span className="flex flex-wrap items-center gap-x-2 text-[13px]">
        <span className="whitespace-nowrap text-n-500">Não configurado</span>
        <Link
          href={`/admin/escolas/whatsapp?tenant=${escola.id}`}
          className="font-semibold text-brand-700 no-underline hover:underline"
        >
          Configurar
        </Link>
      </span>
    );
  }
  const conta = nomeDaConta(escola.waba_id);
  return (
    <span className="flex min-w-0 flex-col gap-[3px]">
      <span className="whitespace-nowrap text-[13px] text-n-900">
        {escola.whatsapp_numero ? formatarTelefone(escola.whatsapp_numero) : "Número não informado"}
      </span>
      <span className="truncate text-xs text-n-500" title={`phone_number_id ${escola.meta_phone_number_id}`}>
        {conta ? (
          <>WABA {conta}</>
        ) : (
          <span
            className="text-[#8A4B00]"
            title="Sem conta do WhatsApp Business: o disparo por template desta escola é recusado, porque não há onde conferir a aprovação."
          >
            Sem conta WABA
          </span>
        )}
        <span className="font-mono text-[11px]"> · ID {escola.meta_phone_number_id}</span>
      </span>
    </span>
  );
}

function ExpedienteDaEscola({ escola }: { escola: Escola }) {
  if (!escola.expediente) return <span className="text-[13px] text-n-500">Não definido</span>;
  return (
    <span className="flex flex-col gap-[3px]">
      <span className="text-[13px] text-n-900">{resumoDias(escola.expediente.dias)}</span>
      <span className="text-xs tabular-nums text-n-500">
        {escola.expediente.inicio} – {escola.expediente.fim}
      </span>
    </span>
  );
}

/* ---------- Ações da linha ------------------------------------------------ */

const BOTAO_LINHA =
  "flex h-9 items-center justify-center gap-1.5 rounded-[9px] border border-n-300 bg-white text-[13px] font-semibold text-n-900 transition-colors hover:border-n-400 hover:bg-n-50";

function AcoesPrincipais({ escola, acoes }: { escola: Escola; acoes: AcoesDaLinha }) {
  // A escola fora do ar mostra a única ação que alguém vem fazer com ela.
  if (escola.licenca.status === "bloqueado") {
    return (
      <button type="button" className={cn(BOTAO_LINHA, "px-3")} onClick={() => acoes.desbloquear(escola)}>
        Desbloquear
      </button>
    );
  }
  if (escola.licenca.status === "cancelado") {
    return (
      <button type="button" className={cn(BOTAO_LINHA, "px-3")} onClick={() => acoes.reativar(escola)}>
        Reativar
      </button>
    );
  }
  const semNumero = !escola.meta_phone_number_id;
  return (
    <>
      <Link href={`/admin/escolas/detalhe?tenant=${escola.id}`} className={cn(BOTAO_LINHA, "px-3 no-underline")}>
        Abrir <ExternalIcon size={14} />
      </Link>
      <button
        type="button"
        aria-label={semNumero ? "Conversas no WhatsApp (não configurado)" : "Conversas no WhatsApp"}
        title={semNumero ? "WhatsApp não configurado" : "Conversas no WhatsApp"}
        disabled={semNumero}
        onClick={() => acoes.conversas(escola)}
        className={cn(
          BOTAO_LINHA,
          "w-9 text-[#146C43]",
          "disabled:cursor-not-allowed disabled:border-n-200 disabled:bg-n-50 disabled:text-n-400",
        )}
      >
        <WhatsAppIcon size={16} />
      </button>
    </>
  );
}

function MenuAcoes({ escola, acoes }: { escola: Escola; acoes: AcoesDaLinha }) {
  const [aberto, setAberto] = useState(false);
  const raiz = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => {
      if (raiz.current && !raiz.current.contains(e.target as Node)) setAberto(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setAberto(false);
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", esc);
    };
  }, [aberto]);

  function item(rotulo: string, icone: ReactNode, fazer: () => void, perigo = false) {
    return (
      <button
        type="button"
        role="menuitem"
        onClick={() => {
          setAberto(false);
          fazer();
        }}
        className={cn(
          "flex h-[38px] items-center gap-2.5 rounded-lg px-2.5 text-left text-sm hover:bg-n-50",
          perigo ? "font-semibold text-[#B42325]" : "text-n-900",
        )}
      >
        {icone}
        {rotulo}
      </button>
    );
  }

  const separador = <div className="mx-1 my-1.5 h-px bg-n-100" />;
  const { status } = escola.licenca;

  return (
    <div ref={raiz} className="relative">
      <button
        type="button"
        aria-label="Mais ações"
        aria-haspopup="menu"
        aria-expanded={aberto}
        onClick={() => setAberto((v) => !v)}
        className={cn(
          BOTAO_LINHA,
          "w-9",
          aberto ? "border-brand-600 bg-brand-50 text-brand-700" : "text-n-700",
        )}
      >
        <DotsIcon size={16} />
      </button>
      {aberto && (
        <div
          role="menu"
          aria-label={`Ações de ${escola.nome}`}
          className="absolute right-0 top-[calc(100%+6px)] z-20 flex w-[232px] flex-col rounded-xl border border-n-200 bg-white p-1.5 shadow-lg"
        >
          {item("Editar dados", <PencilIcon size={16} />, () => acoes.editar(escola))}
          {item("Gerenciar licença", <CardIcon size={16} />, () => acoes.licenca(escola))}
          <Link
            role="menuitem"
            href={`/admin/escolas/whatsapp?tenant=${escola.id}`}
            className="flex h-[38px] items-center gap-2.5 rounded-lg px-2.5 text-sm text-n-900 no-underline hover:bg-n-50"
          >
            <WhatsAppIcon size={16} />
            Número na Meta
          </Link>
          {separador}
          {status === "bloqueado"
            ? item("Desbloquear acesso", <UnlockIcon size={16} />, () => acoes.desbloquear(escola))
            : status === "ativo" && item("Bloquear acesso", <LockIcon size={16} />, () => acoes.bloquear(escola))}
          {status === "cancelado"
            ? item("Reativar assinatura", <UnlockIcon size={16} />, () => acoes.reativar(escola))
            : status === "ativo" && item("Cancelar assinatura", <XCircleIcon size={16} />, () => acoes.cancelar(escola))}
          {separador}
          {item("Excluir escola…", <TrashIcon size={16} />, () => acoes.excluir(escola), true)}
        </div>
      )}
    </div>
  );
}

/* ---------- Painel lateral: nova escola / editar -------------------------- */

/** Escolhe a conta (WABA) da escola.

Existe porque a conta deixou de ser uma variável de ambiente: com mais de uma, é ela que
diz **onde** o template desta escola é criado e conferido. Contas inativas não aparecem —
exceto a que já está escolhida, que precisa continuar visível para não sumir em silêncio
na próxima edição. */
function SeletorDeConta({
  contas,
  valor,
  onChange,
}: {
  contas: ContaWhatsApp[];
  valor: string;
  onChange: (v: string) => void;
}) {
  const visiveis = contas.filter((c) => c.ativo || c.id === valor);
  return (
    <Select id="esc-waba" value={valor} onChange={(e) => onChange(e.target.value)}>
      <option value="">Sem conta vinculada</option>
      {visiveis.map((c) => (
        <option key={c.id} value={c.id}>
          {c.nome}
          {c.meta_waba_id ? ` · ${c.meta_waba_id}` : " · sem id na Meta"}
          {c.ativo ? "" : " (inativa)"}
        </option>
      ))}
    </Select>
  );
}

function Campo({
  id,
  rotulo,
  obrigatorio = false,
  dica,
  erro,
  children,
}: {
  id: string;
  rotulo: string;
  obrigatorio?: boolean;
  dica?: ReactNode;
  erro?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-semibold text-n-900">
        {rotulo}
        {obrigatorio && <span className="text-[#A32022]"> *</span>}
      </label>
      {children}
      {erro ? (
        <span className="text-xs text-danger">{erro}</span>
      ) : dica ? (
        <span className="text-xs leading-snug text-n-500">{dica}</span>
      ) : null}
    </div>
  );
}

function Secao({
  numero,
  titulo,
  opcional = false,
  children,
}: {
  numero: number;
  titulo: string;
  opcional?: boolean;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="flex h-[22px] w-[22px] items-center justify-center rounded-full bg-brand-50 text-xs font-bold text-brand-700">
            {numero}
          </span>
          <h3 className="text-[15px] font-bold text-n-900">{titulo}</h3>
        </div>
        {opcional && (
          <span className="rounded-full bg-n-100 px-[9px] py-[3px] text-xs font-semibold text-n-500">
            Opcional
          </span>
        )}
      </div>
      {children}
    </section>
  );
}

function EscolaDrawer({
  escola,
  contas,
  onClose,
  onSalva,
}: {
  escola: Escola | null;
  contas: ContaWhatsApp[];
  onClose: () => void;
  onSalva: () => Promise<void>;
}) {
  const toast = useToast();
  const editando = escola !== null;
  const [nome, setNome] = useState(escola?.nome ?? "");
  const [slug, setSlug] = useState(escola?.slug ?? "");
  // Na edição o slug nunca acompanha o nome: renomear a escola não deve mudar o endereço dela.
  const [slugManual, setSlugManual] = useState(editando);
  const [contato, setContato] = useState(escola?.telefone_contato ?? "");
  const [expediente, setExpediente] = useState<EstadoExpediente>(
    escola?.expediente
      ? { dias: escola.expediente.dias, inicio: escola.expediente.inicio, fim: escola.expediente.fim }
      : EXPEDIENTE_PADRAO,
  );
  // Só uma conta ativa? Ela já vem escolhida — no caso comum não há decisão a tomar.
  const [wabaId, setWabaId] = useState<string>(() => {
    if (escola) return escola.waba_id ?? "";
    const ativas = contas.filter((c) => c.ativo);
    return ativas.length === 1 ? ativas[0].id : "";
  });
  const [whatsapp, setWhatsapp] = useState(escola?.whatsapp_numero ?? "");
  const [metaPhoneId, setMetaPhoneId] = useState(escola?.meta_phone_number_id ?? "");
  const [erros, setErros] = useState<{ nome?: string; contato?: string }>({});
  const [salvando, setSalvando] = useState(false);

  function mudarNome(valor: string) {
    setNome(valor);
    if (!slugManual) setSlug(slugify(valor));
  }

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    const novosErros = {
      nome: nome.trim() ? undefined : "Informe o nome da escola.",
      contato: contato.trim() ? undefined : "Informe o telefone de contato da escola.",
    };
    setErros(novosErros);
    if (novosErros.nome || novosErros.contato) return;

    setSalvando(true);
    try {
      const args = [
        nome.trim(),
        slug.trim(),
        whatsapp.trim(),
        contato.trim(),
        metaPhoneId.trim(),
        paraEntrada(expediente),
        wabaId || null,
      ] as const;
      if (escola) {
        await atualizarEscola(escola.id, ...args);
      } else {
        await criarEscola(...args);
      }
      await onSalva();
      toast({ tone: "success", title: editando ? "Escola atualizada." : "Escola cadastrada." });
      onClose();
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao salvar a escola.",
      });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Drawer
      open
      onClose={onClose}
      title={editando ? "Editar escola" : "Nova escola"}
      description={
        editando
          ? "As mudanças valem na hora — inclusive para o assistente."
          : "Só nome e contato são obrigatórios. O WhatsApp pode ser ligado depois."
      }
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="form-escola" loading={salvando}>
            {editando ? "Salvar alterações" : "Cadastrar escola"}
          </Button>
        </>
      }
    >
      <form id="form-escola" onSubmit={salvar} className="flex flex-col gap-7" noValidate>
        <Secao numero={1} titulo="Identificação">
          <Campo id="f-nome" rotulo="Nome da escola" obrigatorio erro={erros.nome}>
            <Input
              id="f-nome"
              autoFocus
              value={nome}
              onChange={(e) => mudarNome(e.target.value)}
              placeholder="Ex.: Colégio São José"
              invalid={!!erros.nome}
            />
          </Campo>
          <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
            <Campo
              id="f-slug"
              rotulo="Slug"
              dica={editando ? "Mudar o slug muda o endereço da escola." : "Gerado a partir do nome. Edite se quiser."}
            >
              <Input
                id="f-slug"
                mono
                value={slug}
                onChange={(e) => {
                  setSlugManual(true);
                  setSlug(e.target.value);
                }}
                placeholder="colegio-sao-jose"
              />
            </Campo>
            <Campo
              id="f-contato"
              rotulo="Telefone de contato"
              obrigatorio
              dica="Responsável pela escola."
              erro={erros.contato}
            >
              <Input
                id="f-contato"
                type="tel"
                value={contato}
                onChange={(e) => setContato(e.target.value)}
                placeholder="+55 11 99999-8888"
                invalid={!!erros.contato}
              />
            </Campo>
          </div>
        </Secao>

        <div className="h-px bg-n-100" />

        <Secao numero={2} titulo="Expediente da secretaria">
          <CamposExpediente valor={expediente} onChange={setExpediente} />
        </Secao>

        <div className="h-px bg-n-100" />

        <Secao numero={3} titulo="Integração WhatsApp" opcional>
          <Campo
            id="esc-waba"
            rotulo="Conta do WhatsApp (WABA)"
            dica="É a conta que responde pelo catálogo de templates da escola — sem ela, o disparo por template é recusado."
          >
            <SeletorDeConta contas={contas} valor={wabaId} onChange={setWabaId} />
          </Campo>
          <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
            <Campo id="f-numero" rotulo="Número da plataforma">
              <Input
                id="f-numero"
                type="tel"
                value={whatsapp}
                onChange={(e) => setWhatsapp(e.target.value)}
                placeholder="+55 15 99753-6978"
              />
            </Campo>
            <Campo
              id="f-phoneid"
              rotulo="ID do número na Meta"
              dica="phone_number_id, no Meta Business Manager. Sem ele, o WhatsApp recebido pela escola é descartado."
            >
              <Input
                id="f-phoneid"
                mono
                inputMode="numeric"
                value={metaPhoneId}
                onChange={(e) => setMetaPhoneId(e.target.value)}
                placeholder="123456789012345"
              />
            </Campo>
          </div>
          {editando && (
            <p className="text-xs leading-snug text-n-500">
              Para cadastrar e verificar um número novo na Meta, use{" "}
              <Link
                href={`/admin/escolas/whatsapp?tenant=${escola.id}`}
                className="font-semibold text-brand-700"
              >
                Número na Meta
              </Link>
              .
            </p>
          )}
        </Secao>
      </form>
    </Drawer>
  );
}

/* ---------- Modais de licença -------------------------------------------- */

// Converte ISO (com hora) -> "YYYY-MM-DD" para o input[type=date]; "" se vazio.
function paraInputData(iso: string | null): string {
  return iso ? iso.slice(0, 10) : "";
}

// Centavos -> string em reais para o input (ex.: 29900 -> "299.00"); "" se zero.
function centavosParaInput(centavos: number): string {
  return centavos > 0 ? (centavos / 100).toFixed(2) : "";
}

// String em reais do input -> centavos inteiros (ex.: "299,90" -> 29990).
function inputParaCentavos(valor: string): number {
  const limpo = valor.replace(",", ".").trim();
  if (!limpo) return 0;
  return Math.round(parseFloat(limpo) * 100) || 0;
}

interface PropsModalEscola {
  escola: Escola;
  onClose: () => void;
  onMudou: () => Promise<void>;
}

function BloquearModal({ escola, onClose, onMudou }: PropsModalEscola) {
  const toast = useToast();
  const [motivo, setMotivo] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function confirmar() {
    if (!motivo.trim()) {
      toast({ tone: "danger", title: "Informe o motivo do bloqueio." });
      return;
    }
    setSalvando(true);
    try {
      await bloquearEscola(escola.id, motivo.trim());
      onClose();
      await onMudou();
      toast({ tone: "success", title: "Escola bloqueada." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao bloquear." });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`Bloquear "${escola.nome}"`}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancelar
          </Button>
          <Button variant="danger" size="sm" loading={salvando} onClick={confirmar}>
            Bloquear
          </Button>
        </>
      }
    >
      <p className="mb-3 text-sm text-n-500">
        A escola perde acesso ao painel e aos disparos até ser desbloqueada. O motivo fica
        registrado.
      </p>
      <Field label="Motivo do bloqueio">
        <Textarea
          autoFocus
          rows={3}
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
          placeholder="Ex.: Inadimplência — mensalidade de junho/2026 em aberto."
        />
      </Field>
    </Modal>
  );
}

function CancelarModal({ escola, onClose, onMudou }: PropsModalEscola) {
  const toast = useToast();
  const [motivo, setMotivo] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function confirmar() {
    if (!motivo.trim()) {
      toast({ tone: "danger", title: "Informe o motivo do cancelamento." });
      return;
    }
    setSalvando(true);
    try {
      await cancelarEscola(escola.id, motivo.trim());
      onClose();
      await onMudou();
      toast({ tone: "success", title: "Escola cancelada." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao cancelar." });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`Cancelar "${escola.nome}"`}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Voltar
          </Button>
          <Button variant="danger" size="sm" loading={salvando} onClick={confirmar}>
            Cancelar escola
          </Button>
        </>
      }
    >
      <p className="mb-3 text-sm text-n-500">
        O cancelamento registra a <strong>saída</strong> da escola da plataforma (churn): ela
        perde acesso ao painel e aos disparos, e a data/motivo ficam na ficha financeira. É
        reversível por &quot;Reativar&quot;.
      </p>
      <Field label="Motivo do cancelamento">
        <Textarea
          autoFocus
          rows={3}
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
          placeholder="Ex.: Escola encerrou o contrato em junho/2026."
        />
      </Field>
    </Modal>
  );
}

function LicencaModal({ escola, onClose, onMudou }: PropsModalEscola) {
  const toast = useToast();
  const [plano, setPlano] = useState<"mensal" | "anual">(escola.licenca.plano);
  const [expira, setExpira] = useState(paraInputData(escola.licenca.licenca_expira_em));
  const [valorMensal, setValorMensal] = useState(
    centavosParaInput(escola.licenca.valor_mensal_centavos),
  );
  const [valorAnual, setValorAnual] = useState(
    centavosParaInput(escola.licenca.valor_anual_centavos),
  );
  const [salvando, setSalvando] = useState(false);

  async function salvar() {
    setSalvando(true);
    try {
      // input[type=date] devolve "YYYY-MM-DD"; envia null se vazio.
      await definirLicenca(
        escola.id,
        plano,
        expira ? `${expira}T00:00:00Z` : null,
        inputParaCentavos(valorMensal),
        inputParaCentavos(valorAnual),
      );
      onClose();
      await onMudou();
      toast({ tone: "success", title: "Licença atualizada." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao salvar." });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`Licença de "${escola.nome}"`}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancelar
          </Button>
          <Button size="sm" loading={salvando} onClick={salvar}>
            Salvar
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label="Plano">
          <Select value={plano} onChange={(e) => setPlano(e.target.value as "mensal" | "anual")}>
            <option value="mensal">Mensal</option>
            <option value="anual">Anual</option>
          </Select>
        </Field>
        <Field label="Expira em">
          <CampoData value={expira} onChange={setExpira} />
        </Field>
        <div className="flex flex-wrap gap-3">
          <div className="min-w-[140px] flex-1">
            <Field label="Valor mensal (R$)">
              <Input
                inputMode="decimal"
                value={valorMensal}
                onChange={(e) => setValorMensal(e.target.value)}
                placeholder="Ex.: 299.00"
              />
            </Field>
          </div>
          <div className="min-w-[140px] flex-1">
            <Field label="Valor anual (R$)">
              <Input
                inputMode="decimal"
                value={valorAnual}
                onChange={(e) => setValorAnual(e.target.value)}
                placeholder="Ex.: 2990.00"
              />
            </Field>
          </div>
        </div>
        <p className="text-xs text-n-400">
          Os valores alimentam a ficha financeira (MRR/ARR e receita acumulada). No plano anual, a
          plataforma avisa os admins por e-mail quando a licença está perto de vencer.
        </p>
      </div>
    </Modal>
  );
}
