"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  adicionarConhecimento,
  FonteConhecimento,
  getSessao,
  listarConhecimento,
  logout,
  removerConhecimento,
  Usuario,
} from "@/lib/admin";

const TIPOS = [
  { valor: "procedimento", rotulo: "Procedimento" },
  { valor: "aviso", rotulo: "Aviso" },
  { valor: "faq", rotulo: "FAQ" },
];

export default function BaseDeConhecimento() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [fontes, setFontes] = useState<FonteConhecimento[]>([]);
  const [erro, setErro] = useState("");

  const recarregar = useCallback(async () => {
    setFontes(await listarConhecimento());
  }, []);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    recarregar().catch(() => setErro("Falha ao carregar documentos."));
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
          <span className="font-semibold">TI-Escolar — Base de conhecimento</span>
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

      <div className="mx-auto max-w-5xl space-y-6 p-6">
        {erro && (
          <div className="flex items-center justify-between rounded bg-red-100 px-4 py-2 text-sm text-red-700">
            <span>{erro}</span>
            <button onClick={() => setErro("")} className="text-red-500 hover:text-red-700">
              ✕
            </button>
          </div>
        )}

        <p className="rounded-xl bg-blue-50 px-4 py-3 text-sm text-blue-800">
          📚 Os documentos enviados aqui são fragmentados e indexados para enriquecer as respostas
          do assistente sobre os <b>procedimentos desta escola</b>. Valem apenas para este tenant.
        </p>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-[1fr_1fr]">
          <NovoDocumento onMudou={recarregar} onErro={setErro} />
          <ListaDocumentos fontes={fontes} onMudou={recarregar} onErro={setErro} />
        </div>
      </div>
    </main>
  );
}

function NovoDocumento({
  onMudou,
  onErro,
}: {
  onMudou: () => Promise<void>;
  onErro: (e: string) => void;
}) {
  const [nome, setNome] = useState("");
  const [tipo, setTipo] = useState("procedimento");
  const [conteudo, setConteudo] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [ok, setOk] = useState("");

  async function lerArquivo(e: React.ChangeEvent<HTMLInputElement>) {
    const arquivo = e.target.files?.[0];
    if (!arquivo) return;
    const texto = await arquivo.text();
    setConteudo(texto);
    if (!nome.trim()) setNome(arquivo.name.replace(/\.[^.]+$/, ""));
  }

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim() || !conteudo.trim()) return;
    setSalvando(true);
    setOk("");
    try {
      const fonte = await adicionarConhecimento(nome.trim(), conteudo, tipo);
      setOk(`✓ "${fonte.nome}" indexado em ${fonte.total_trechos} trecho(s).`);
      setNome("");
      setConteudo("");
      await onMudou();
    } catch (err) {
      onErro(err instanceof Error ? err.message : "Falha ao enviar documento.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <section className="rounded-xl bg-white p-5 shadow">
      <h2 className="mb-3 font-semibold text-slate-800">Enviar documento</h2>
      <form onSubmit={enviar} className="space-y-3">
        <div className="flex gap-2">
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder="Nome do documento"
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-wa-header"
          />
          <select
            value={tipo}
            onChange={(e) => setTipo(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-wa-header"
          >
            {TIPOS.map((t) => (
              <option key={t.valor} value={t.valor}>
                {t.rotulo}
              </option>
            ))}
          </select>
        </div>

        <label className="block text-xs text-slate-500">
          Carregar de um arquivo de texto (.txt/.md) — opcional:
          <input
            type="file"
            accept=".txt,.md,text/plain,text/markdown"
            onChange={lerArquivo}
            className="mt-1 block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-sm hover:file:bg-slate-200"
          />
        </label>

        <textarea
          value={conteudo}
          onChange={(e) => setConteudo(e.target.value)}
          placeholder="Cole aqui o conteúdo do documento (procedimentos, regras, avisos)…"
          rows={10}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-wa-header"
        />

        <button
          disabled={salvando}
          className="rounded-lg bg-wa-header px-5 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          {salvando ? "Indexando…" : "Indexar documento"}
        </button>

        {ok && <div className="rounded-lg bg-green-50 p-3 text-sm text-green-800">{ok}</div>}
      </form>
    </section>
  );
}

function ListaDocumentos({
  fontes,
  onMudou,
  onErro,
}: {
  fontes: FonteConhecimento[];
  onMudou: () => Promise<void>;
  onErro: (e: string) => void;
}) {
  async function excluir(f: FonteConhecimento) {
    if (!window.confirm(`Remover "${f.nome}" da base de conhecimento?`)) return;
    try {
      await removerConhecimento(f.id);
      await onMudou();
    } catch (err) {
      onErro(err instanceof Error ? err.message : "Falha ao remover documento.");
    }
  }

  return (
    <section className="rounded-xl bg-white p-5 shadow">
      <h2 className="mb-3 font-semibold text-slate-800">
        Documentos indexados · {fontes.length}
      </h2>
      <ul className="divide-y">
        {fontes.map((f) => (
          <li key={f.id} className="flex items-center justify-between py-3 text-sm">
            <div>
              <p className="text-slate-700">{f.nome}</p>
              <p className="text-xs text-slate-400">
                <span className="rounded bg-slate-100 px-1.5 py-0.5 capitalize">{f.tipo}</span>{" "}
                · {f.total_trechos} trecho(s) ·{" "}
                {new Date(f.criado_em).toLocaleDateString("pt-BR")}
              </p>
            </div>
            <button
              onClick={() => excluir(f)}
              className="text-xs text-red-500 hover:text-red-700"
            >
              Remover
            </button>
          </li>
        ))}
        {fontes.length === 0 && (
          <li className="py-2 text-sm text-slate-400">Nenhum documento enviado ainda.</li>
        )}
      </ul>
    </section>
  );
}
