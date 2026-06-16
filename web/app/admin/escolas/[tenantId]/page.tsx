"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  BroadcastResumo,
  ConversaDetalhe,
  ConversaResumo,
  Escola,
  getSessao,
  listarBroadcasts,
  listarConversas,
  logout,
  obterConversa,
  obterEscola,
  Usuario,
} from "@/lib/admin";

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
  const params = useParams<{ tenantId: string }>();
  const tenantId = params.tenantId;

  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [escola, setEscola] = useState<Escola | null>(null);
  const [aba, setAba] = useState<Aba>("conversas");
  const [conversas, setConversas] = useState<ConversaResumo[]>([]);
  const [broadcasts, setBroadcasts] = useState<BroadcastResumo[]>([]);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(true);

  const recarregar = useCallback(async () => {
    const [e, cs, bs] = await Promise.all([
      obterEscola(tenantId),
      listarConversas(tenantId),
      listarBroadcasts(tenantId),
    ]);
    setEscola(e);
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
        setErro(err instanceof Error ? err.message : "Falha ao carregar a escola.")
      )
      .finally(() => setCarregando(false));
  }, [router, recarregar]);

  function sair() {
    logout();
    router.replace("/admin/login");
  }

  if (!usuario) return null;

  return (
    <main className="min-h-screen bg-slate-100">
      <header className="flex items-center justify-between bg-wa-header px-6 py-3 text-white">
        <div className="flex items-center gap-2">
          <span className="text-xl">🎓</span>
          <span className="font-semibold">
            {escola ? escola.nome : "Escola"} — visão da escola
          </span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <Link href="/admin/escolas" className="text-white/80 hover:text-white">
            ← Escolas
          </Link>
          <button onClick={sair} className="rounded bg-white/15 px-3 py-1 hover:bg-white/25">
            Sair
          </button>
        </div>
      </header>

      <div className="mx-auto max-w-5xl space-y-6 p-6">
        {erro && (
          <div className="rounded bg-red-100 px-4 py-2 text-sm text-red-700">{erro}</div>
        )}

        {/* Abas */}
        <div className="flex gap-2">
          <button
            onClick={() => setAba("conversas")}
            className={`rounded-lg px-4 py-2 text-sm font-medium ${
              aba === "conversas"
                ? "bg-wa-header text-white"
                : "bg-white text-slate-600 shadow hover:bg-slate-50"
            }`}
          >
            💬 Conversas ({conversas.length})
          </button>
          <button
            onClick={() => setAba("broadcasts")}
            className={`rounded-lg px-4 py-2 text-sm font-medium ${
              aba === "broadcasts"
                ? "bg-wa-header text-white"
                : "bg-white text-slate-600 shadow hover:bg-slate-50"
            }`}
          >
            📣 Mensagens em massa ({broadcasts.length})
          </button>
        </div>

        {carregando ? (
          <p className="text-sm text-slate-400">Carregando…</p>
        ) : aba === "conversas" ? (
          <ConversasAba tenantId={tenantId} conversas={conversas} onErro={setErro} />
        ) : (
          <BroadcastsAba broadcasts={broadcasts} />
        )}
      </div>
    </main>
  );
}

function ConversasAba({
  tenantId,
  conversas,
  onErro,
}: {
  tenantId: string;
  conversas: ConversaResumo[];
  onErro: (e: string) => void;
}) {
  const [aberta, setAberta] = useState<ConversaDetalhe | null>(null);
  const [carregandoId, setCarregandoId] = useState<string | null>(null);

  async function abrir(id: string) {
    setCarregandoId(id);
    onErro("");
    try {
      setAberta(await obterConversa(tenantId, id));
    } catch (err) {
      onErro(err instanceof Error ? err.message : "Falha ao abrir conversa.");
    } finally {
      setCarregandoId(null);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-[320px_1fr]">
      <section className="rounded-xl bg-white p-3 shadow">
        {conversas.length === 0 ? (
          <p className="p-3 text-sm text-slate-400">
            Nenhuma conversa iniciada pelos pais ainda.
          </p>
        ) : (
          <ul className="space-y-1">
            {conversas.map((c) => (
              <li key={c.id}>
                <button
                  onClick={() => abrir(c.id)}
                  className={`w-full rounded-lg px-3 py-2 text-left ${
                    aberta?.id === c.id ? "bg-wa-header text-white" : "hover:bg-slate-100"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-sm">{c.contato}</span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs ${
                        aberta?.id === c.id ? "bg-white/20" : "bg-slate-200 text-slate-600"
                      }`}
                    >
                      {c.total_mensagens}
                    </span>
                  </div>
                  <p
                    className={`truncate text-xs ${
                      aberta?.id === c.id ? "text-white/80" : "text-slate-500"
                    }`}
                  >
                    {c.ultima_mensagem || "sem mensagens"}
                  </p>
                  <p
                    className={`text-[10px] ${
                      aberta?.id === c.id ? "text-white/60" : "text-slate-400"
                    }`}
                  >
                    {formatar(c.ultima_em ?? c.criado_em)}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl bg-white p-5 shadow">
        {carregandoId ? (
          <p className="text-sm text-slate-400">Carregando conversa…</p>
        ) : !aberta ? (
          <p className="flex h-full items-center justify-center text-sm text-slate-400">
            Selecione uma conversa para ver as mensagens trocadas com a IA.
          </p>
        ) : (
          <div>
            <div className="mb-4 border-b pb-2">
              <h2 className="font-semibold text-slate-800">{aberta.contato}</h2>
              <p className="text-xs text-slate-400">
                Iniciada em {formatar(aberta.criado_em)} · {aberta.mensagens.length} mensagens
              </p>
            </div>
            <div className="space-y-2">
              {aberta.mensagens.map((m) => (
                <div
                  key={m.id}
                  className={`flex ${m.autor === "usuario" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${
                      m.autor === "usuario"
                        ? "bg-wa-out text-slate-800"
                        : "bg-slate-100 text-slate-800"
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{m.texto}</p>
                    {m.fontes.length > 0 && (
                      <p className="mt-1 text-[10px] text-slate-500">
                        Fontes: {m.fontes.join(", ")}
                      </p>
                    )}
                    <p className="mt-1 text-right text-[10px] text-slate-400">
                      {formatar(m.criado_em)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>
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

function BroadcastsAba({ broadcasts }: { broadcasts: BroadcastResumo[] }) {
  if (broadcasts.length === 0) {
    return (
      <section className="rounded-xl bg-white p-10 text-center text-sm text-slate-400 shadow">
        Nenhuma mensagem em massa enviada por esta escola ainda.
      </section>
    );
  }

  return (
    <section className="rounded-xl bg-white p-5 shadow">
      <ul className="divide-y">
        {broadcasts.map((b) => (
          <li key={b.id} className="py-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="font-medium text-slate-800">{b.titulo}</h3>
                <p className="text-xs text-slate-400">{formatar(b.criado_em)}</p>
              </div>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                {ROTULO_STATUS[b.status] ?? b.status}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-500">
              <span className="font-medium text-slate-700">
                {b.total_destinatarios} destinatário(s)
              </span>
              {Object.entries(b.por_status).map(([st, n]) => (
                <span key={st} className="rounded bg-slate-50 px-2 py-0.5">
                  {st}: {n}
                </span>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
