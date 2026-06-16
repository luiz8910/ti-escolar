"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { getSessao, logout, obterPrompt, salvarPrompt, Usuario } from "@/lib/admin";

const EXEMPLO =
  "Ex.: Trate os responsáveis pelo primeiro nome. Reforce o uso obrigatório do uniforme. " +
  "Para assuntos formais, oriente o e-mail secretaria@escola.test. Nunca compartilhe notas " +
  "de um aluno com quem não seja o responsável cadastrado.";

export default function InstrucoesDaEscola() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [conteudo, setConteudo] = useState("");
  const [atualizadoEm, setAtualizadoEm] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [ok, setOk] = useState("");
  const [erro, setErro] = useState("");

  const carregar = useCallback(async () => {
    const p = await obterPrompt();
    setConteudo(p.conteudo);
    setAtualizadoEm(p.atualizado_em);
  }, []);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    carregar().catch(() => setErro("Falha ao carregar as instruções."));
  }, [router, carregar]);

  function sair() {
    logout();
    router.replace("/admin/login");
  }

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    setSalvando(true);
    setOk("");
    setErro("");
    try {
      const p = await salvarPrompt(conteudo);
      setAtualizadoEm(p.atualizado_em);
      setOk("✓ Instruções salvas. O assistente já as utilizará nas próximas conversas.");
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Falha ao salvar.");
    } finally {
      setSalvando(false);
    }
  }

  if (!usuario) return null;

  return (
    <main className="min-h-screen bg-slate-100">
      <header className="flex items-center justify-between bg-wa-header px-6 py-3 text-white">
        <div className="flex items-center gap-2">
          <span className="text-xl">🎓</span>
          <span className="font-semibold">TI-Escolar — Instruções da escola</span>
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

      <div className="mx-auto max-w-3xl space-y-6 p-6">
        {erro && (
          <div className="flex items-center justify-between rounded bg-red-100 px-4 py-2 text-sm text-red-700">
            <span>{erro}</span>
            <button onClick={() => setErro("")} className="text-red-500 hover:text-red-700">
              ✕
            </button>
          </div>
        )}

        <p className="rounded-xl bg-blue-50 px-4 py-3 text-sm text-blue-800">
          🧭 Estas instruções funcionam como um <b>&ldquo;CLAUDE.md&rdquo; da sua escola</b>: são
          anexadas às diretrizes do assistente e têm prioridade institucional. Use para ajustar tom,
          regras de privacidade e contexto específico deste tenant.
        </p>

        <section className="rounded-xl bg-white p-5 shadow">
          <form onSubmit={salvar} className="space-y-3">
            <textarea
              value={conteudo}
              onChange={(e) => setConteudo(e.target.value)}
              placeholder={EXEMPLO}
              rows={14}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-wa-header"
            />
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">
                {atualizadoEm
                  ? `Atualizado em ${new Date(atualizadoEm).toLocaleString("pt-BR")}`
                  : "Ainda não definido"}
              </span>
              <button
                disabled={salvando}
                className="rounded-lg bg-wa-header px-5 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
              >
                {salvando ? "Salvando…" : "Salvar instruções"}
              </button>
            </div>
            {ok && <div className="rounded-lg bg-green-50 p-3 text-sm text-green-800">{ok}</div>}
          </form>
        </section>
      </div>
    </main>
  );
}
