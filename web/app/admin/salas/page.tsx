"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  atualizarPai,
  atualizarSala,
  cadastrarPai,
  criarSala,
  desvincularPaiDaSala,
  getSessao,
  listarPais,
  listarSalas,
  logout,
  Pai,
  relatorioPaisDaSala,
  removerPai,
  removerSala,
  Sala,
  Usuario,
  vincularPaiASala,
} from "@/lib/admin";

export default function SalasEPais() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [salas, setSalas] = useState<Sala[]>([]);
  const [pais, setPais] = useState<Pai[]>([]);
  const [selecionada, setSelecionada] = useState<Sala | null>(null);
  const [erro, setErro] = useState("");

  const recarregar = useCallback(async () => {
    const [ss, ps] = await Promise.all([listarSalas(), listarPais()]);
    setSalas(ss);
    setPais(ps);
    setSelecionada((atual) => (atual ? ss.find((s) => s.id === atual.id) ?? null : null));
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

  return (
    <main className="min-h-screen bg-slate-100">
      <header className="flex items-center justify-between bg-wa-header px-6 py-3 text-white">
        <div className="flex items-center gap-2">
          <span className="text-xl">🎓</span>
          <span className="font-semibold">TI-Escolar — Salas e pais</span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <a href="/admin" className="text-white/80 hover:text-white">
            ← Painel
          </a>
          <span>
            {usuario.nome}{" "}
            <span className="rounded bg-white/20 px-2 py-0.5 text-xs">
              {usuario.papel === "super_admin" ? "Super Admin" : "Admin da escola"}
            </span>
          </span>
          <button onClick={sair} className="rounded bg-white/15 px-3 py-1 hover:bg-white/25">
            Sair
          </button>
        </div>
      </header>

      <div className="mx-auto max-w-6xl space-y-6 p-6">
        {erro && (
          <div className="flex items-center justify-between rounded bg-red-100 px-4 py-2 text-sm text-red-700">
            <span>{erro}</span>
            <button onClick={() => setErro("")} className="text-red-500 hover:text-red-700">
              ✕
            </button>
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[340px_1fr]">
          {/* Salas */}
          <SalasPanel
            salas={salas}
            selecionada={selecionada}
            onSelecionar={setSelecionada}
            onMudou={recarregar}
            onErro={setErro}
          />

          {/* Detalhe da sala selecionada (relatório de pais) */}
          <SalaDetalhe
            sala={selecionada}
            pais={pais}
            onMudou={recarregar}
            onErro={setErro}
          />
        </div>

        {/* Cadastro de pais (CRUD) */}
        <PaisPanel pais={pais} onMudou={recarregar} onErro={setErro} />
      </div>
    </main>
  );
}

// --------------------------------------------------------------------------- //
function SalasPanel({
  salas,
  selecionada,
  onSelecionar,
  onMudou,
  onErro,
}: {
  salas: Sala[];
  selecionada: Sala | null;
  onSelecionar: (s: Sala) => void;
  onMudou: () => Promise<void>;
  onErro: (e: string) => void;
}) {
  const [nova, setNova] = useState("");

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    if (!nova.trim()) return;
    try {
      await criarSala(nova.trim());
      setNova("");
      await onMudou();
    } catch (err) {
      onErro(err instanceof Error ? err.message : "Não foi possível criar a sala.");
    }
  }

  async function renomear(sala: Sala) {
    const nome = window.prompt("Novo nome da sala:", sala.nome);
    if (!nome || nome.trim() === sala.nome) return;
    try {
      await atualizarSala(sala.id, nome.trim(), sala.descricao);
      await onMudou();
    } catch (err) {
      onErro(err instanceof Error ? err.message : "Falha ao renomear.");
    }
  }

  async function excluir(sala: Sala) {
    if (!window.confirm(`Excluir a sala "${sala.nome}"? Os pais continuam cadastrados.`)) return;
    try {
      await removerSala(sala.id);
      await onMudou();
    } catch (err) {
      onErro(err instanceof Error ? err.message : "Falha ao excluir.");
    }
  }

  return (
    <section className="rounded-xl bg-white p-5 shadow">
      <h2 className="mb-3 font-semibold text-slate-800">Salas (turmas)</h2>
      <ul className="space-y-1">
        {salas.map((s) => (
          <li
            key={s.id}
            className={`flex items-center justify-between rounded-lg px-3 py-2 text-sm ${
              selecionada?.id === s.id ? "bg-wa-header text-white" : "text-slate-700 hover:bg-slate-100"
            }`}
          >
            <button onClick={() => onSelecionar(s)} className="flex-1 text-left">
              {s.nome}{" "}
              <span
                className={`ml-1 rounded-full px-2 py-0.5 text-xs ${
                  selecionada?.id === s.id ? "bg-white/20" : "bg-slate-200 text-slate-600"
                }`}
              >
                {s.total_pais}
              </span>
            </button>
            <span className="ml-2 flex gap-2 text-xs">
              <button onClick={() => renomear(s)} title="Renomear" className="opacity-70 hover:opacity-100">
                ✏️
              </button>
              <button onClick={() => excluir(s)} title="Excluir" className="opacity-70 hover:opacity-100">
                🗑️
              </button>
            </span>
          </li>
        ))}
        {salas.length === 0 && (
          <li className="px-3 py-2 text-sm text-slate-400">Nenhuma sala cadastrada.</li>
        )}
      </ul>

      <form onSubmit={criar} className="mt-4 flex gap-2 border-t pt-4">
        <input
          value={nova}
          onChange={(e) => setNova(e.target.value)}
          placeholder="Nova sala (ex.: 4ª série B)"
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-wa-header"
        />
        <button className="rounded-lg bg-wa-header px-3 text-sm text-white hover:opacity-90">
          + Criar
        </button>
      </form>
    </section>
  );
}

// --------------------------------------------------------------------------- //
function SalaDetalhe({
  sala,
  pais,
  onMudou,
  onErro,
}: {
  sala: Sala | null;
  pais: Pai[];
  onMudou: () => Promise<void>;
  onErro: (e: string) => void;
}) {
  const [relatorio, setRelatorio] = useState<Pai[]>([]);
  const [paiId, setPaiId] = useState("");

  const carregarRelatorio = useCallback(async () => {
    if (!sala) {
      setRelatorio([]);
      return;
    }
    try {
      setRelatorio(await relatorioPaisDaSala(sala.id));
    } catch (err) {
      onErro(err instanceof Error ? err.message : "Falha ao carregar relatório.");
    }
  }, [sala, onErro]);

  useEffect(() => {
    carregarRelatorio();
  }, [carregarRelatorio]);

  if (!sala) {
    return (
      <section className="flex items-center justify-center rounded-xl bg-white p-10 text-sm text-slate-400 shadow">
        Selecione uma sala para ver o relatório de pais e gerenciar vínculos.
      </section>
    );
  }

  const naVinculados = pais.filter((p) => !relatorio.some((r) => r.id === p.id));

  async function vincular(e: React.FormEvent) {
    e.preventDefault();
    if (!paiId) return;
    try {
      await vincularPaiASala(sala!.id, paiId);
      setPaiId("");
      await Promise.all([carregarRelatorio(), onMudou()]);
    } catch (err) {
      onErro(err instanceof Error ? err.message : "Falha ao vincular.");
    }
  }

  async function desvincular(p: Pai) {
    try {
      await desvincularPaiDaSala(sala!.id, p.id);
      await Promise.all([carregarRelatorio(), onMudou()]);
    } catch (err) {
      onErro(err instanceof Error ? err.message : "Falha ao desvincular.");
    }
  }

  function imprimir() {
    window.print();
  }

  return (
    <section className="space-y-4 rounded-xl bg-white p-5 shadow">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-slate-800">
          Relatório — {sala.nome} · {relatorio.length} responsável(is)
        </h2>
        <button
          onClick={imprimir}
          className="rounded-lg border border-slate-300 px-3 py-1 text-sm text-slate-600 hover:bg-slate-50"
        >
          🖨️ Imprimir / PDF
        </button>
      </div>

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-slate-500">
            <th className="py-2">Responsável</th>
            <th className="py-2">WhatsApp</th>
            <th className="py-2 text-right">Ações</th>
          </tr>
        </thead>
        <tbody>
          {relatorio.map((p) => (
            <tr key={p.id} className="border-b last:border-0">
              <td className="py-2 text-slate-700">{p.nome}</td>
              <td className="py-2 font-mono text-slate-500">{p.telefone}</td>
              <td className="py-2 text-right">
                <button
                  onClick={() => desvincular(p)}
                  className="text-xs text-red-500 hover:text-red-700 print:hidden"
                >
                  Remover da sala
                </button>
              </td>
            </tr>
          ))}
          {relatorio.length === 0 && (
            <tr>
              <td colSpan={3} className="py-3 text-slate-400">
                Nenhum responsável vinculado a esta sala.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <form onSubmit={vincular} className="flex gap-2 border-t pt-4 print:hidden">
        <select
          value={paiId}
          onChange={(e) => setPaiId(e.target.value)}
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-wa-header"
        >
          <option value="">Vincular responsável já cadastrado…</option>
          {naVinculados.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nome} — {p.telefone}
            </option>
          ))}
        </select>
        <button
          disabled={!paiId}
          className="rounded-lg bg-slate-700 px-4 text-sm text-white hover:opacity-90 disabled:opacity-50"
        >
          + Vincular
        </button>
      </form>
    </section>
  );
}

// --------------------------------------------------------------------------- //
function PaisPanel({
  pais,
  onMudou,
  onErro,
}: {
  pais: Pai[];
  onMudou: () => Promise<void>;
  onErro: (e: string) => void;
}) {
  const [nome, setNome] = useState("");
  const [telefone, setTelefone] = useState("");
  const [editando, setEditando] = useState<string | null>(null);

  async function adicionar(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim() || !telefone.trim()) return;
    try {
      if (editando) {
        await atualizarPai(editando, nome.trim(), telefone.trim());
      } else {
        await cadastrarPai(nome.trim(), telefone.trim());
      }
      setNome("");
      setTelefone("");
      setEditando(null);
      await onMudou();
    } catch (err) {
      onErro(err instanceof Error ? err.message : "Falha ao salvar responsável.");
    }
  }

  function editar(p: Pai) {
    setEditando(p.id);
    setNome(p.nome);
    setTelefone(p.telefone);
  }

  function cancelar() {
    setEditando(null);
    setNome("");
    setTelefone("");
  }

  async function excluir(p: Pai) {
    if (!window.confirm(`Excluir o responsável "${p.nome}"?`)) return;
    try {
      await removerPai(p.id);
      await onMudou();
    } catch (err) {
      onErro(err instanceof Error ? err.message : "Falha ao excluir.");
    }
  }

  return (
    <section className="rounded-xl bg-white p-5 shadow">
      <h2 className="mb-3 font-semibold text-slate-800">
        Pais / responsáveis cadastrados · {pais.length}
      </h2>

      <form onSubmit={adicionar} className="mb-4 flex flex-wrap gap-2">
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
        <button className="rounded-lg bg-wa-header px-4 text-sm text-white hover:opacity-90">
          {editando ? "Salvar" : "+ Cadastrar"}
        </button>
        {editando && (
          <button
            type="button"
            onClick={cancelar}
            className="rounded-lg border border-slate-300 px-3 text-sm text-slate-600 hover:bg-slate-50"
          >
            Cancelar
          </button>
        )}
      </form>

      <ul className="divide-y">
        {pais.map((p) => (
          <li key={p.id} className="flex items-center justify-between py-2 text-sm">
            <span className="text-slate-700">{p.nome}</span>
            <span className="flex items-center gap-3">
              <span className="font-mono text-slate-500">{p.telefone}</span>
              <button onClick={() => editar(p)} className="text-xs text-slate-500 hover:text-slate-700">
                Editar
              </button>
              <button onClick={() => excluir(p)} className="text-xs text-red-500 hover:text-red-700">
                Excluir
              </button>
            </span>
          </li>
        ))}
        {pais.length === 0 && (
          <li className="py-2 text-sm text-slate-400">Nenhum responsável cadastrado ainda.</li>
        )}
      </ul>
    </section>
  );
}
