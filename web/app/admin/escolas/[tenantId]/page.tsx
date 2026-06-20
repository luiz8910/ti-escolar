"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  BroadcastResumo,
  ConversaDetalhe,
  ConversaResumo,
  Escola,
  FichaFinanceira,
  getSessao,
  listarBroadcasts,
  listarConversas,
  logout,
  obterConversa,
  obterEscola,
  obterFichaFinanceira,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/components/ui/cn";
import { LicencaBadge } from "@/components/admin/LicencaBadge";
import { ChatBubbleIcon, BellIcon } from "@/components/ui/icons";

// Centavos -> "R$ 1.234,56".
function formatarMoeda(centavos: number): string {
  return (centavos / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

type Aba = "conversas" | "broadcasts";

function formatar(data: string | null): string {
  if (!data) return "—";
  return new Date(data).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function EscolaDetalhePage() {
  const router = useRouter();
  const toast = useToast();
  const params = useParams<{ tenantId: string }>();
  const tenantId = params.tenantId;

  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [escola, setEscola] = useState<Escola | null>(null);
  const [ficha, setFicha] = useState<FichaFinanceira | null>(null);
  const [aba, setAba] = useState<Aba>("conversas");
  const [conversas, setConversas] = useState<ConversaResumo[]>([]);
  const [broadcasts, setBroadcasts] = useState<BroadcastResumo[]>([]);
  const [carregando, setCarregando] = useState(true);

  const recarregar = useCallback(async () => {
    const [e, f, cs, bs] = await Promise.all([
      obterEscola(tenantId),
      obterFichaFinanceira(tenantId),
      listarConversas(tenantId),
      listarBroadcasts(tenantId),
    ]);
    setEscola(e);
    setFicha(f);
    setConversas(cs);
    setBroadcasts(bs);
  }, [tenantId]);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    recarregar()
      .catch((err) =>
        toast({
          tone: "danger",
          title: err instanceof Error ? err.message : "Falha ao carregar a escola.",
        })
      )
      .finally(() => setCarregando(false));
  }, [router, recarregar, toast]);

  function sair() {
    logout();
    router.replace("/admin/login");
  }

  if (!usuario) return null;

  return (
    <AppShell
      title={escola ? escola.nome : "Escola"}
      user={{ name: usuario.nome, role: "Super Admin" }}
      tenantName="Plataforma"
      isSuperAdmin
      onLogout={sair}
    >
      <div className="flex flex-col gap-[18px]">
        {escola && <LicencaInfo escola={escola} />}

        {ficha && <FichaFinanceiraCard ficha={ficha} />}

        {/* Abas segmentadas */}
        <div className="inline-flex w-fit gap-1 rounded-lg border border-n-200 bg-white p-1 shadow-sm">
          <Segment active={aba === "conversas"} onClick={() => setAba("conversas")}>
            <ChatBubbleIcon size={16} /> Conversas
            <span className="ml-1 text-n-400">{conversas.length}</span>
          </Segment>
          <Segment active={aba === "broadcasts"} onClick={() => setAba("broadcasts")}>
            <BellIcon size={16} /> Mensagens em massa
            <span className="ml-1 text-n-400">{broadcasts.length}</span>
          </Segment>
        </div>

        {carregando ? (
          <p className="text-sm text-n-400">Carregando…</p>
        ) : aba === "conversas" ? (
          <ConversasAba tenantId={tenantId} conversas={conversas} />
        ) : (
          <BroadcastsAba broadcasts={broadcasts} />
        )}
      </div>
    </AppShell>
  );
}

function LicencaInfo({ escola }: { escola: Escola }) {
  const l = escola.licenca;
  return (
    <Card className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <LicencaBadge licenca={l} />
        <div className="text-xs text-n-500">
          <span className="font-semibold text-n-700">
            Plano {l.plano === "anual" ? "anual" : "mensal"}
          </span>
          {l.licenca_expira_em && <> · expira em {formatar(l.licenca_expira_em)}</>}
        </div>
      </div>
      {l.status === "bloqueado" && l.motivo_bloqueio && (
        <p className="text-xs text-danger">Motivo do bloqueio: {l.motivo_bloqueio}</p>
      )}
      {l.status === "cancelado" && l.motivo_cancelamento && (
        <p className="text-xs text-n-500">
          Cancelada {l.cancelado_em ? `em ${formatar(l.cancelado_em)}` : ""} ·{" "}
          {l.motivo_cancelamento}
        </p>
      )}
    </Card>
  );
}

const ROTULO_PAGAMENTO: Record<string, string> = {
  em_dia: "Em dia",
  a_vencer: "A vencer",
  vencido: "Vencido",
  inadimplente: "Inadimplente",
  cancelado: "Cancelado",
};

const TONE_PAGAMENTO: Record<string, "neutral" | "brand" | "success" | "warning" | "danger"> = {
  em_dia: "success",
  a_vencer: "warning",
  vencido: "danger",
  inadimplente: "danger",
  cancelado: "neutral",
};

function Metrica({ rotulo, valor }: { rotulo: string; valor: string | number }) {
  return (
    <div className="rounded-[10px] border border-n-100 bg-n-50/60 px-3 py-2.5">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-n-400">{rotulo}</p>
      <p className="mt-0.5 text-sm font-bold text-n-900">{valor}</p>
    </div>
  );
}

function FichaFinanceiraCard({ ficha }: { ficha: FichaFinanceira }) {
  const corSaude =
    ficha.health_score >= 70
      ? "text-success"
      : ficha.health_score >= 40
        ? "text-warning"
        : "text-danger";
  const cota =
    ficha.limite_diario_meta < 0
      ? "ilimitada"
      : `${ficha.limite_diario_meta.toLocaleString("pt-BR")}/dia`;

  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-bold text-n-900">Ficha financeira</h2>
        <div className="flex items-center gap-2">
          <Badge tone={TONE_PAGAMENTO[ficha.status_pagamento] ?? "neutral"}>
            {ROTULO_PAGAMENTO[ficha.status_pagamento] ?? ficha.status_pagamento}
          </Badge>
          <span className={cn("text-xs font-bold", corSaude)} title="Health score (0–100)">
            Saúde {ficha.health_score}
          </span>
        </div>
      </div>

      {/* Ciclo de vida e cobrança */}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
        <Metrica
          rotulo="Início"
          valor={`${formatar(ficha.criado_em)} (${ficha.dias_de_casa}d)`}
        />
        <Metrica rotulo="Plano" valor={ficha.plano === "anual" ? "Anual" : "Mensal"} />
        <Metrica
          rotulo="Próxima renovação"
          valor={ficha.licenca_expira_em ? formatar(ficha.licenca_expira_em) : "—"}
        />
        <Metrica rotulo="Meses ativos" valor={ficha.meses_ativos} />
        <Metrica rotulo="Valor mensal" valor={formatarMoeda(ficha.valor_mensal_centavos)} />
        <Metrica rotulo="Valor anual" valor={formatarMoeda(ficha.valor_anual_centavos)} />
        <Metrica rotulo="MRR" valor={formatarMoeda(ficha.mrr_centavos)} />
        <Metrica rotulo="ARR" valor={formatarMoeda(ficha.arr_centavos)} />
        <Metrica
          rotulo="Receita acumulada (LTV est.)"
          valor={formatarMoeda(ficha.receita_acumulada_centavos)}
        />
        <Metrica rotulo="Cota de envio (Meta)" valor={cota} />
      </div>

      {ficha.cancelado_em && (
        <p className="mt-3 text-xs text-n-500">
          <span className="font-semibold text-n-700">Cancelada</span> em{" "}
          {formatar(ficha.cancelado_em)}
          {ficha.motivo_cancelamento ? ` · ${ficha.motivo_cancelamento}` : ""}
        </p>
      )}

      {/* Uso */}
      <div className="mt-4 border-t border-n-100 pt-3">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-n-400">
          Uso da plataforma
        </p>
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
          <Metrica rotulo="Usuários ativos" valor={ficha.uso.total_usuarios_ativos} />
          <Metrica rotulo="Contatos" valor={ficha.uso.total_contatos} />
          <Metrica rotulo="Alunos" valor={ficha.uso.total_alunos} />
          <Metrica rotulo="Conversas" valor={ficha.uso.total_conversas} />
          <Metrica rotulo="Mensagens em massa" valor={ficha.uso.total_broadcasts} />
        </div>
      </div>
    </Card>
  );
}

function Segment({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-3.5 py-2 text-[13px] font-semibold transition-colors",
        active ? "bg-brand-600 text-white" : "text-n-600 hover:bg-n-50"
      )}
    >
      {children}
    </button>
  );
}

function ConversasAba({
  tenantId,
  conversas,
}: {
  tenantId: string;
  conversas: ConversaResumo[];
}) {
  const toast = useToast();
  const [aberta, setAberta] = useState<ConversaDetalhe | null>(null);
  const [carregandoId, setCarregandoId] = useState<string | null>(null);

  async function abrir(id: string) {
    setCarregandoId(id);
    try {
      setAberta(await obterConversa(tenantId, id));
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao abrir conversa." });
    } finally {
      setCarregandoId(null);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-[18px] lg:grid-cols-[300px_1fr]">
      <Card className="p-3">
        {conversas.length === 0 ? (
          <p className="p-3 text-sm text-n-400">Nenhuma conversa iniciada pelos pais ainda.</p>
        ) : (
          <div className="flex flex-col gap-1">
            {conversas.map((c) => {
              const active = aberta?.id === c.id;
              return (
                <button
                  key={c.id}
                  onClick={() => abrir(c.id)}
                  className={cn(
                    "w-full rounded-[10px] px-3 py-2.5 text-left",
                    active ? "bg-brand-600 text-white" : "hover:bg-n-50"
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[13px] font-semibold">{c.contato}</span>
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-[11px] font-bold",
                        active ? "bg-white/20" : "bg-n-100 text-n-500"
                      )}
                    >
                      {c.total_mensagens}
                    </span>
                  </div>
                  <p className={cn("mt-0.5 truncate text-xs", active ? "text-white/80" : "text-n-500")}>
                    {c.ultima_mensagem || "sem mensagens"}
                  </p>
                  <p className={cn("text-[10px]", active ? "text-white/60" : "text-n-400")}>
                    {formatar(c.ultima_em ?? c.criado_em)}
                  </p>
                </button>
              );
            })}
          </div>
        )}
      </Card>

      <Card>
        {carregandoId ? (
          <p className="text-sm text-n-400">Carregando conversa…</p>
        ) : !aberta ? (
          <div className="flex h-full items-center justify-center">
            <EmptyState
              icon={<ChatBubbleIcon size={24} />}
              title="Selecione uma conversa"
              description="Escolha uma conversa à esquerda para ver as mensagens trocadas com a IA."
            />
          </div>
        ) : (
          <div>
            <div className="mb-4 border-b border-n-100 pb-3">
              <h2 className="text-sm font-bold text-n-900">{aberta.contato}</h2>
              <p className="text-xs text-n-400">
                Iniciada em {formatar(aberta.criado_em)} · {aberta.mensagens.length} mensagens
              </p>
            </div>
            <div className="flex flex-col gap-2">
              {aberta.mensagens.map((m) => (
                <div
                  key={m.id}
                  className={cn("flex", m.autor === "usuario" ? "justify-end" : "justify-start")}
                >
                  <div
                    className={cn(
                      "max-w-[80%] rounded-2xl px-3.5 py-2.5 text-[13px]",
                      m.autor === "usuario" ? "bg-brand-50 text-n-900" : "bg-n-100 text-n-900"
                    )}
                  >
                    <p className="whitespace-pre-wrap leading-relaxed">{m.texto}</p>
                    {m.fontes.length > 0 && (
                      <p className="mt-1 text-[10px] text-n-500">Fontes: {m.fontes.join(", ")}</p>
                    )}
                    <p className="mt-1 text-right text-[10px] text-n-400">{formatar(m.criado_em)}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

const ROTULO_STATUS: Record<string, string> = {
  rascunho: "Rascunho",
  agendado: "Agendado",
  em_envio: "Em envio",
  concluido: "Concluído",
  parcial_limite: "Parcial (cota)",
};

const TONE_STATUS: Record<string, "neutral" | "brand" | "success" | "warning"> = {
  rascunho: "neutral",
  agendado: "brand",
  em_envio: "brand",
  concluido: "success",
  parcial_limite: "warning",
};

function BroadcastsAba({ broadcasts }: { broadcasts: BroadcastResumo[] }) {
  if (broadcasts.length === 0) {
    return (
      <Card className="flex items-center justify-center py-10">
        <EmptyState
          icon={<BellIcon size={24} />}
          title="Nenhuma mensagem em massa"
          description="Esta escola ainda não enviou nenhum disparo para os responsáveis."
        />
      </Card>
    );
  }

  return (
    <Card>
      <div className="flex flex-col">
        {broadcasts.map((b) => (
          <div key={b.id} className="border-t border-n-100 py-4 first:border-t-0 first:pt-0">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-bold text-n-900">{b.titulo}</h3>
                <p className="text-xs text-n-400">{formatar(b.criado_em)}</p>
              </div>
              <Badge tone={TONE_STATUS[b.status] ?? "neutral"}>
                {ROTULO_STATUS[b.status] ?? b.status}
              </Badge>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-n-500">
              <span className="font-semibold text-n-700">
                {b.total_destinatarios} destinatário(s)
              </span>
              {Object.entries(b.por_status).map(([st, n]) => (
                <span key={st} className="rounded bg-n-50 px-2 py-0.5">
                  {st}: {n}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
