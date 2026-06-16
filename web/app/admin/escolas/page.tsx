"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  atualizarEscola,
  criarEscola,
  Escola,
  getSessao,
  listarEscolas,
  logout,
  removerEscola,
  Usuario,
} from "@/lib/admin";

export default function EscolasPage() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [escolas, setEscolas] = useState<Escola[]>([]);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(true);

  const recarregar = useCallback(async () => {
    const es = await listarEscolas();
    setEscolas(es);
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
      .catch(() => setErro("Falha ao carregar escolas."))
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
          <span className="font-semibold">TI-Escolar — Escolas (Super Admin)</span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <Link href="/admin" className="text-white/80 hover:text-white">
            Grupos &amp; disparos
          </Link>
          <span>
            {usuario.nome}{" "}
            <span className="rounded bg-white/20 px-2 py-0.5 text-xs">Super Admin</span>
          </span>
          <button onClick={sair} className="rounded bg-white/15 px-3 py-1 hover:bg-white/25">
            Sair
          </button>
        </div>
      </header>

      <div className="mx-auto max-w-5xl space-y-6 p-6">
        {erro && (
          <div className="rounded bg-red-100 px-4 py-2 text-sm text-red-700">{erro}</div>
        )}

        <NovaEscola onCriada={recarregar} onErro={setErro} />

        <section className="rounded-xl bg-white p-5 shadow">
          <h2 className="mb-4 font-semibold text-slate-800">
            Escolas cadastradas ({escolas.length})
          </h2>
          {carregando ? (
            <p className="text-sm text-slate-400">Carregando…</p>
          ) : escolas.length === 0 ? (
            <p className="text-sm text-slate-400">Nenhuma escola cadastrada ainda.</p>
          ) : (
            <ul className="divide-y">
              {escolas.map((e) => (
                <EscolaLinha
                  key={e.id}
                  escola={e}
                  onMudou={recarregar}
                  onErro={setErro}
                />
              ))}
            </ul>
          )}
        </section>
      </div>
    </main>
  );
}

function NovaEscola({
  onCriada,
  onErro,
}: {
  onCriada: () => Promise<void>;
  onErro: (e: string) => void;
}) {
  const [nome, setNome] = useState("");
  const [slug, setSlug] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim()) return;
    setSalvando(true);
    onErro("");
    try {
      await criarEscola(nome.trim(), slug.trim());
      setNome("");
      setSlug("");
      await onCriada();
    } catch (err) {
      onErro(err instanceof Error ? err.message : "Falha ao criar escola.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <section className="rounded-xl bg-white p-5 shadow">
      <h2 className="mb-3 font-semibold text-slate-800">Cadastrar escola</h2>
      <form onSubmit={criar} className="flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[200px]">
          <label className="mb-1 block text-xs font-medium text-slate-600">Nome</label>
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder="Ex.: Colégio São José"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-wa-header"
          />
        </div>
        <div className="min-w-[180px]">
          <label className="mb-1 block text-xs font-medium text-slate-600">
            Slug (opcional)
          </label>
          <input
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="derivado do nome"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-wa-header"
          />
        </div>
        <button
          disabled={salvando}
          className="rounded-lg bg-wa-header px-5 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          {salvando ? "Salvando…" : "+ Cadastrar"}
        </button>
      </form>
    </section>
  );
}

function EscolaLinha({
  escola,
  onMudou,
  onErro,
}: {
  escola: Escola;
  onMudou: () => Promise<void>;
  onErro: (e: string) => void;
}) {
  const [editando, setEditando] = useState(false);
  const [nome, setNome] = useState(escola.nome);
  const [slug, setSlug] = useState(escola.slug);

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    onErro("");
    try {
      await atualizarEscola(escola.id, nome.trim(), slug.trim());
      setEditando(false);
      await onMudou();
    } catch (err) {
      onErro(err instanceof Error ? err.message : "Falha ao salvar.");
    }
  }

  async function excluir() {
    if (
      !window.confirm(
        `Excluir "${escola.nome}" e TODOS os seus dados (conversas, contatos, mensagens)? Esta ação é irreversível.`
      )
    )
      return;
    onErro("");
    try {
      await removerEscola(escola.id);
      await onMudou();
    } catch (err) {
      onErro(err instanceof Error ? err.message : "Falha ao excluir.");
    }
  }

  if (editando) {
    return (
      <li className="py-3">
        <form onSubmit={salvar} className="flex flex-wrap items-center gap-2">
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            className="flex-1 min-w-[180px] rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-wa-header"
          />
          <input
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            className="w-44 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-wa-header"
          />
          <button className="rounded-lg bg-wa-header px-4 py-2 text-sm text-white hover:opacity-90">
            Salvar
          </button>
          <button
            type="button"
            onClick={() => {
              setEditando(false);
              setNome(escola.nome);
              setSlug(escola.slug);
            }}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-100"
          >
            Cancelar
          </button>
        </form>
      </li>
    );
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div>
        <Link
          href={`/admin/escolas/${escola.id}`}
          className="font-medium text-slate-800 hover:text-wa-header hover:underline"
        >
          {escola.nome}
        </Link>
        <p className="font-mono text-xs text-slate-400">{escola.slug}</p>
      </div>
      <div className="flex items-center gap-4 text-xs text-slate-500">
        <span title="Conversas">💬 {escola.total_conversas}</span>
        <span title="Contatos">👪 {escola.total_contatos}</span>
        <span title="Mensagens em massa">📣 {escola.total_broadcasts}</span>
      </div>
      <div className="flex items-center gap-2">
        <Link
          href={`/admin/escolas/${escola.id}`}
          className="rounded-lg bg-slate-100 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-200"
        >
          Abrir
        </Link>
        <button
          onClick={() => setEditando(true)}
          className="rounded-lg bg-slate-100 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-200"
        >
          Editar
        </button>
        <button
          onClick={excluir}
          className="rounded-lg bg-red-50 px-3 py-1.5 text-sm text-red-600 hover:bg-red-100"
        >
          Excluir
        </button>
      </div>
    </li>
  );
}
