"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  adicionarContato,
  consultarQuota,
  criarGrupo,
  enviarParaGrupo,
  getSessao,
  Grupo,
  logout,
  Quota,
  listarGrupos,
  ResultadoEnvioGrupo,
  Usuario,
} from "@/lib/admin";

export default function AdminDashboard() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [grupos, setGrupos] = useState<Grupo[]>([]);
  const [quota, setQuota] = useState<Quota | null>(null);
  const [selecionado, setSelecionado] = useState<Grupo | null>(null);
  const [erro, setErro] = useState("");

  const recarregar = useCallback(async () => {
    const [gs, q] = await Promise.all([listarGrupos(), consultarQuota()]);
    setGrupos(gs);
    setQuota(q);
    setSelecionado((atual) => (atual ? gs.find((g) => g.id === atual.id) ?? null : null));
  }, []);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    recarregar().catch(() => setErro("Falha ao carregar dados."));
  }, [router, recarregar]);

  function sair() {
    logout();
    router.replace("/admin/login");
  }

  if (!usuario) return null;

  const pct =
    quota && quota.limite_diario > 0
      ? Math.min(100, Math.round((quota.enviados / quota.limite_diario) * 100))
      : 0;

  return (
    <main className="min-h-screen bg-slate-100">
      {/* Cabeçalho */}
      <header className="flex items-center justify-between bg-wa-header px-6 py-3 text-white">
        <div className="flex items-center gap-2">
          <span className="text-xl">🎓</span>
          <span className="font-semibold">TI-Escolar — Painel administrativo</span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          {usuario.papel === "super_admin" && (
            <a href="/admin/escolas" className="text-white/80 hover:text-white">
              Escolas
            </a>
          )}
          <span>
            {usuario.nome}{" "}
            <span className="rounded bg-white/20 px-2 py-0.5 text-xs">
              {usuario.papel === "super_admin" ? "Super Admin" : "Admin da escola"}
            </span>
          </span>
          <a href="/" className="text-white/80 hover:text-white">
            Ver demo ↗
          </a>
          <button onClick={sair} className="rounded bg-white/15 px-3 py-1 hover:bg-white/25">
            Sair
          </button>
        </div>
      </header>

      <div className="mx-auto max-w-5xl space-y-6 p-6">
        {erro && <div className="rounded bg-red-100 px-4 py-2 text-sm text-red-700">{erro}</div>}

        {/* Cota diária (tier Meta) */}
        {quota && (
          <section className="rounded-xl bg-white p-5 shadow">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="font-semibold text-slate-800">Cota diária de mensagens (Meta)</h2>
              <span className="text-sm text-slate-500">{quota.dia}</span>
            </div>
            <div className="h-3 w-full overflow-hidden rounded-full bg-slate-200">
              <div
                className={`h-full rounded-full ${pct >= 100 ? "bg-red-500" : "bg-wa-header"}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <p className="mt-2 text-sm text-slate-600">
              {quota.enviados} enviados ·{" "}
              {quota.limite_diario < 0 ? "ilimitado" : `limite ${quota.limite_diario}`} ·{" "}
              <span className="font-medium">{quota.restante}</span> restantes hoje
            </p>
          </section>
        )}

        <div className="grid grid-cols-1 gap-6 md:grid-cols-[320px_1fr]">
          {/* Lista de grupos */}
          <GruposPanel
            grupos={grupos}
            selecionado={selecionado}
            onSelecionar={setSelecionado}
            onCriado={recarregar}
            onErro={setErro}
          />

          {/* Detalhe do grupo */}
          <GrupoDetalhe grupo={selecionado} onMudou={recarregar} onErro={setErro} />
        </div>
      </div>
    </main>
  );
}

function GruposPanel({
  grupos,
  selecionado,
  onSelecionar,
  onCriado,
  onErro,
}: {
  grupos: Grupo[];
  selecionado: Grupo | null;
  onSelecionar: (g: Grupo) => void;
  onCriado: () => Promise<void>;
  onErro: (e: string) => void;
}) {
  const [novo, setNovo] = useState("");

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    if (!novo.trim()) return;
    try {
      await criarGrupo(novo.trim(), "");
      setNovo("");
      await onCriado();
    } catch {
      onErro("Não foi possível criar o grupo.");
    }
  }

  return (
    <section className="rounded-xl bg-white p-5 shadow">
      <h2 className="mb-3 font-semibold text-slate-800">Grupos</h2>
      <ul className="space-y-1">
        {grupos.map((g) => (
          <li key={g.id}>
            <button
              onClick={() => onSelecionar(g)}
              className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm ${
                selecionado?.id === g.id
                  ? "bg-wa-header text-white"
                  : "text-slate-700 hover:bg-slate-100"
              }`}
            >
              <span>{g.nome}</span>
              <span
                className={`rounded-full px-2 py-0.5 text-xs ${
                  selecionado?.id === g.id ? "bg-white/20" : "bg-slate-200 text-slate-600"
                }`}
              >
                {g.total_membros}
              </span>
            </button>
          </li>
        ))}
        {grupos.length === 0 && (
          <li className="px-3 py-2 text-sm text-slate-400">Nenhum grupo ainda.</li>
        )}
      </ul>

      <form onSubmit={criar} className="mt-4 flex gap-2 border-t pt-4">
        <input
          value={novo}
          onChange={(e) => setNovo(e.target.value)}
          placeholder="Novo grupo…"
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-wa-header"
        />
        <button className="rounded-lg bg-wa-header px-3 text-sm text-white hover:opacity-90">
          + Criar
        </button>
      </form>
    </section>
  );
}

function GrupoDetalhe({
  grupo,
  onMudou,
  onErro,
}: {
  grupo: Grupo | null;
  onMudou: () => Promise<void>;
  onErro: (e: string) => void;
}) {
  const [nome, setNome] = useState("");
  const [telefone, setTelefone] = useState("");
  const [titulo, setTitulo] = useState("");
  const [mensagem, setMensagem] = useState("");
  const [resultado, setResultado] = useState<ResultadoEnvioGrupo | null>(null);
  const [enviando, setEnviando] = useState(false);

  if (!grupo) {
    return (
      <section className="flex items-center justify-center rounded-xl bg-white p-10 text-sm text-slate-400 shadow">
        Selecione um grupo para gerenciar contatos e enviar mensagens.
      </section>
    );
  }

  async function addContato(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim() || !telefone.trim()) return;
    try {
      await adicionarContato(grupo!.id, nome.trim(), telefone.trim());
      setNome("");
      setTelefone("");
      await onMudou();
    } catch (err) {
      onErro(err instanceof Error ? err.message : "Falha ao adicionar contato.");
    }
  }

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (!titulo.trim() || !mensagem.trim()) return;
    setEnviando(true);
    setResultado(null);
    try {
      const r = await enviarParaGrupo(grupo!.id, titulo.trim(), mensagem.trim());
      setResultado(r);
      setTitulo("");
      setMensagem("");
      await onMudou();
    } catch (err) {
      onErro(err instanceof Error ? err.message : "Falha ao enviar.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section className="space-y-6">
      {/* Membros */}
      <div className="rounded-xl bg-white p-5 shadow">
        <h2 className="mb-3 font-semibold text-slate-800">
          {grupo.nome} · {grupo.total_membros} contato(s)
        </h2>
        <ul className="mb-4 divide-y">
          {grupo.membros.map((c) => (
            <li key={c.id} className="flex items-center justify-between py-2 text-sm">
              <span className="text-slate-700">{c.nome}</span>
              <span className="font-mono text-slate-500">{c.telefone}</span>
            </li>
          ))}
          {grupo.membros.length === 0 && (
            <li className="py-2 text-sm text-slate-400">Sem contatos neste grupo.</li>
          )}
        </ul>

        <form onSubmit={addContato} className="flex flex-wrap gap-2 border-t pt-4">
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder="Nome do responsável"
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-wa-header"
          />
          <input
            value={telefone}
            onChange={(e) => setTelefone(e.target.value)}
            placeholder="+5511999990000"
            className="w-44 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-wa-header"
          />
          <button className="rounded-lg bg-slate-700 px-4 text-sm text-white hover:opacity-90">
            + Contato
          </button>
        </form>
      </div>

      {/* Envio direcionado */}
      <div className="rounded-xl bg-white p-5 shadow">
        <h2 className="mb-1 font-semibold text-slate-800">Enviar mensagem ao grupo</h2>
        <p className="mb-3 text-xs text-slate-500">
          Usa o template aprovado e respeita a cota diária. Alcança apenas os {grupo.total_membros}{" "}
          contato(s) de <b>{grupo.nome}</b>.
        </p>
        <form onSubmit={enviar} className="space-y-3">
          <input
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="Título (ex.: Reunião de pais)"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-wa-header"
          />
          <textarea
            value={mensagem}
            onChange={(e) => setMensagem(e.target.value)}
            placeholder="Mensagem aos responsáveis…"
            rows={3}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-wa-header"
          />
          <button
            disabled={enviando}
            className="rounded-lg bg-wa-header px-5 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {enviando ? "Enviando…" : `Enviar para ${grupo.total_membros} contato(s)`}
          </button>
        </form>

        {resultado && (
          <div className="mt-4 rounded-lg bg-green-50 p-3 text-sm text-green-800">
            ✓ Disparo concluído — <b>{resultado.broadcast.enviados}</b> enviados
            {resultado.broadcast.falhas > 0 && `, ${resultado.broadcast.falhas} falhas`}
            {resultado.broadcast.bloqueados_por_limite > 0 &&
              `, ${resultado.broadcast.bloqueados_por_limite} bloqueados pela cota`}
            . Restam {resultado.broadcast.restante_cota} na cota de hoje.
          </div>
        )}
      </div>
    </section>
  );
}
