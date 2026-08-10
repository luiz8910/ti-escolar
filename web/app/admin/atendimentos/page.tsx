"use client";

/**
 * Fila de atendimento humano (§6j).
 *
 * O que chega aqui é o que o assistente não resolveu **e** o responsável aceitou levar a
 * uma pessoa. A tela é feita para uma decisão só: quem está esperando há mais tempo?
 * Por isso a ordem é por espera (não por novidade) e o card mostra o motivo já resumido
 * pelo assistente — quem atende não deveria ter que reler a conversa para saber do que
 * se trata.
 *
 * O aviso da **janela de 24h** aparece antes de a pessoa digitar. Descobrir que a
 * resposta não pode sair depois de escrevê-la é a pior ordem possível.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  Atendimento,
  AtendimentoDetalhe,
  assumirAtendimento,
  getSessao,
  listarAtendimentos,
  logout,
  obterAtendimento,
  reabrirAtendimento,
  resolverAtendimento,
  responderAtendimento,
  StatusAtendimento,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/form";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import {
  Paginacao,
  PaginaMeta,
  salvarTamanhoPreferido,
  tamanhoPreferido,
} from "@/components/ui/Paginacao";

const STATUS_LABEL: Record<StatusAtendimento, string> = {
  oferecido: "Oferecido",
  aberto: "Aguardando",
  em_atendimento: "Em atendimento",
  resolvido: "Resolvido",
  descartado: "Descartado",
};
const STATUS_TONE: Record<
  StatusAtendimento,
  "neutral" | "brand" | "success" | "warning" | "danger"
> = {
  oferecido: "neutral",
  aberto: "warning",
  em_atendimento: "brand",
  resolvido: "success",
  descartado: "neutral",
};

type Aba = "fila" | "meus" | "resolvido";

const ABAS: { chave: Aba; rotulo: string; status: string; meus: boolean }[] = [
  { chave: "fila", rotulo: "Na fila", status: "", meus: false },
  { chave: "meus", rotulo: "Meus", status: "aberto,em_atendimento", meus: true },
  { chave: "resolvido", rotulo: "Resolvidos", status: "resolvido", meus: false },
];

/** "há 3 min" / "há 2 h 10" — o dado que decide a ordem de atendimento. */
function espera(minutos: number): string {
  if (minutos < 1) return "agora";
  if (minutos < 60) return `há ${minutos} min`;
  const horas = Math.floor(minutos / 60);
  const resto = minutos % 60;
  return resto ? `há ${horas} h ${resto}` : `há ${horas} h`;
}

function hora(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function FilaDeAtendimento() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [aba, setAba] = useState<Aba>("fila");
  const [itens, setItens] = useState<Atendimento[]>([]);
  const [meta, setMeta] = useState<PaginaMeta>({
    pagina: 1,
    por_pagina: 25,
    total: 0,
    total_paginas: 1,
  });
  const [aberto, setAberto] = useState<AtendimentoDetalhe | null>(null);
  const toast = useToast();

  const carregar = useCallback(
    async (pagina = 1, porPagina?: number) => {
      const cfg = ABAS.find((a) => a.chave === aba)!;
      const dados = await listarAtendimentos({
        status: cfg.status,
        meus: cfg.meus,
        pagina,
        porPagina: porPagina ?? tamanhoPreferido("atendimentos", 25),
      });
      setItens(dados.itens);
      setMeta(dados.meta);
    },
    [aba],
  );

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    carregar().catch(() => toast({ tone: "danger", title: "Falha ao carregar a fila." }));
  }, [router, carregar, toast]);

  async function abrir(id: string) {
    try {
      setAberto(await obterAtendimento(id));
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha." });
    }
  }

  async function agir(fn: () => Promise<unknown>, sucesso: string) {
    try {
      await fn();
      await carregar(meta.pagina);
      if (aberto) setAberto(await obterAtendimento(aberto.atendimento.id));
      toast({ tone: "success", title: sucesso });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha." });
    }
  }

  if (!usuario) return null;

  return (
    <AppShell
      title="Atendimentos"
      user={{
        name: usuario.nome,
        role: usuario.papel === "super_admin" ? "Super Admin" : "Admin da escola",
      }}
      tenantName="Escola Demonstração"
      isSuperAdmin={usuario.papel === "super_admin"}
      onLogout={() => {
        logout();
        router.replace("/admin/login");
      }}
    >
      <div className="flex flex-col gap-[18px]">
        <Card>
          <CardHeader
            title="Fila da secretaria"
            action={
              <div className="flex gap-1 rounded-lg bg-n-100 p-1">
                {ABAS.map((a) => (
                  <button
                    key={a.chave}
                    onClick={() => setAba(a.chave)}
                    className={
                      "rounded-md px-3 py-1.5 text-[12.5px] font-semibold transition-colors " +
                      (aba === a.chave
                        ? "bg-white text-n-900 shadow-sm"
                        : "text-n-500 hover:text-n-700")
                    }
                  >
                    {a.rotulo}
                  </button>
                ))}
              </div>
            }
          />
          <p className="mb-3 text-sm text-n-500">
            Conversas que o assistente encaminhou depois de o responsável confirmar que
            queria falar com alguém. A resposta sai pelo mesmo WhatsApp da escola, no
            mesmo fio da conversa.
          </p>

          {itens.length === 0 ? (
            <EmptyState
              title="Nada na fila"
              description="Quando o assistente não resolver e o responsável aceitar falar com a secretaria, o caso aparece aqui."
            />
          ) : (
            <div className="flex flex-col gap-3">
              {itens.map((a) => (
                <CardAtendimento
                  key={a.id}
                  item={a}
                  onAbrir={() => abrir(a.id)}
                  onAssumir={() =>
                    agir(() => assumirAtendimento(a.id), "Atendimento assumido.")
                  }
                />
              ))}
            </div>
          )}

          <Paginacao
            meta={meta}
            rotulo="atendimento(s)"
            onPagina={(p) => carregar(p)}
            onTamanho={(t) => {
              salvarTamanhoPreferido("atendimentos", t);
              carregar(1, t);
            }}
          />
        </Card>

        {aberto && (
          <Conversa
            detalhe={aberto}
            usuarioId={usuario.id}
            onFechar={() => setAberto(null)}
            onResponder={(texto) =>
              agir(
                () => responderAtendimento(aberto.atendimento.id, texto),
                "Resposta enviada ao responsável.",
              )
            }
            onResolver={() =>
              agir(
                () => resolverAtendimento(aberto.atendimento.id),
                "Atendimento resolvido.",
              )
            }
            onReabrir={() =>
              agir(() => reabrirAtendimento(aberto.atendimento.id), "Atendimento reaberto.")
            }
          />
        )}
      </div>
    </AppShell>
  );
}

function CardAtendimento({
  item,
  onAbrir,
  onAssumir,
}: {
  item: Atendimento;
  onAbrir: () => void;
  onAssumir: () => void;
}) {
  return (
    <div className="rounded-xl border border-n-200 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-n-900">
              {item.contato_nome || item.contato}
            </span>
            <Badge tone={STATUS_TONE[item.status]}>{STATUS_LABEL[item.status]}</Badge>
            {item.fora_expediente && (
              <Badge tone="neutral">Chegou fora do expediente</Badge>
            )}
            {!item.janela_aberta && (
              <Badge tone="danger">Janela de 24h expirada</Badge>
            )}
          </div>
          <p className="mt-1.5 text-sm text-n-600">
            {item.motivo || "Sem resumo do assistente."}
          </p>
          <p className="mt-1 text-[12px] text-n-400">
            {item.contato} · aguardando {espera(item.minutos_de_espera)}
            {item.atendente_nome && ` · com ${item.atendente_nome}`}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          {!item.atendente_id && item.status !== "resolvido" && (
            <Button variant="secondary" onClick={onAssumir}>
              Assumir
            </Button>
          )}
          <Button onClick={onAbrir}>Abrir conversa</Button>
        </div>
      </div>
    </div>
  );
}

function Conversa({
  detalhe,
  usuarioId,
  onFechar,
  onResponder,
  onResolver,
  onReabrir,
}: {
  detalhe: AtendimentoDetalhe;
  usuarioId: string;
  onFechar: () => void;
  onResponder: (texto: string) => Promise<void>;
  onResolver: () => Promise<void>;
  onReabrir: () => Promise<void>;
}) {
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const a = detalhe.atendimento;
  // Outra pessoa já assumiu: a caixa some, porque duas respostas pelo mesmo número
  // chegam ao responsável como duas vozes da escola se contradizendo.
  const deOutraPessoa = Boolean(a.atendente_id && a.atendente_id !== usuarioId);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (!texto.trim()) return;
    setEnviando(true);
    try {
      await onResponder(texto.trim());
      setTexto("");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title={`Conversa com ${a.contato_nome || a.contato}`}
        action={
          <div className="flex gap-2">
            {a.status === "resolvido" ? (
              <Button variant="secondary" onClick={onReabrir}>
                Reabrir
              </Button>
            ) : (
              <Button variant="secondary" onClick={onResolver}>
                Marcar como resolvido
              </Button>
            )}
            <Button variant="ghost" onClick={onFechar}>
              Fechar
            </Button>
          </div>
        }
      />

      <div className="mb-3 flex flex-col gap-2 rounded-lg bg-n-50 p-3 text-[12.5px] text-n-600">
        <span>
          <strong>Motivo:</strong> {a.motivo || "—"}
        </span>
        <span>
          {a.janela_aberta ? (
            <>Você pode responder em texto livre até {hora(a.janela_expira_em)}.</>
          ) : (
            <span className="text-danger">
              A janela de 24h do WhatsApp expirou. Só um template aprovado pela Meta
              reabre esta conversa — sem ele, o envio será recusado.
            </span>
          )}
        </span>
      </div>

      <div className="mb-4 flex max-h-[420px] flex-col gap-2 overflow-y-auto">
        {detalhe.mensagens.map((m, i) => (
          <div
            key={i}
            className={
              "max-w-[80%] rounded-xl px-3 py-2 text-sm " +
              (m.autor === "usuario"
                ? "self-start bg-n-100 text-n-800"
                : m.autor === "atendente"
                  ? "self-end bg-brand-500 text-white"
                  : "self-end bg-brand-50 text-brand-900")
            }
          >
            <p className="mb-0.5 text-[11px] opacity-70">
              {m.autor === "usuario"
                ? "Responsável"
                : m.autor === "atendente"
                  ? m.autor_nome || "Secretaria"
                  : "Assistente"}{" "}
              · {hora(m.criado_em)}
            </p>
            <p className="whitespace-pre-wrap">{m.texto}</p>
            {m.fontes.length > 0 && (
              <p className="mt-1 text-[11px] opacity-70">Fontes: {m.fontes.join(", ")}</p>
            )}
          </div>
        ))}
      </div>

      {deOutraPessoa ? (
        <p className="text-sm text-n-500">
          Este atendimento está com <strong>{a.atendente_nome}</strong>. Peça para ela
          liberar antes de responder.
        </p>
      ) : (
        <form onSubmit={enviar} className="flex flex-col gap-2">
          <Textarea
            rows={3}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Escreva a resposta ao responsável…"
          />
          <div className="flex justify-end">
            <Button type="submit" disabled={enviando || !texto.trim()}>
              {enviando ? "Enviando…" : "Enviar pelo WhatsApp da escola"}
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}
