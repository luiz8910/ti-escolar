"use client";

/**
 * Tela de erro do painel (item 6 do checklist de pré-deploy).
 *
 * Sem este arquivo, um erro de runtime cai na tela padrão do Next: em produção, uma
 * página em branco com "Application error" e nada que a secretaria possa relatar.
 *
 * Duas decisões:
 * - **Mostrar o código de correlação** quando ele existe. O back-end devolve o
 *   `id_correlacao` em todo erro; exibi-lo é o que transforma "o sistema deu erro ontem"
 *   em uma linha localizável no painel de Logs.
 * - **Nunca mostrar a mensagem técnica crua** ao usuário. Ela vai para o console do
 *   navegador, onde quem está depurando a encontra.
 */

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[ti-escolar] erro na interface:", error);
  }, [error]);

  // O back-end anexa o id ao corpo do erro; quando a falha é só do cliente, sobra o
  // `digest` que o próprio Next gera.
  const codigo =
    (error as { id_correlacao?: string }).id_correlacao ?? error.digest ?? "";

  return (
    <main className="flex min-h-[70vh] flex-col items-center justify-center px-6 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-danger/10 text-danger">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
          <path d="M12 4 2.7 20h18.6L12 4Z" />
          <path d="M12 10v4" />
          <path d="M12 17.2v.1" />
        </svg>
      </div>

      <h1 className="mt-5 text-[19px] font-extrabold text-n-900">
        Algo deu errado por aqui
      </h1>
      <p className="mt-2 max-w-[420px] text-[13.5px] leading-relaxed text-n-500">
        A página não conseguiu carregar. Você pode tentar de novo — nenhum dado foi
        perdido. Se continuar acontecendo, informe o código abaixo ao suporte.
      </p>

      {codigo && (
        <p className="mt-4 rounded-lg bg-n-50 px-3 py-2 font-mono text-[12px] text-n-600">
          código: {codigo}
        </p>
      )}

      <div className="mt-6 flex gap-2">
        <button
          onClick={reset}
          className="rounded-[10px] bg-brand-600 px-4 py-2.5 text-[13px] font-bold text-white hover:bg-brand-700"
        >
          Tentar novamente
        </button>
        <a
          href="/admin"
          className="rounded-[10px] border border-n-200 px-4 py-2.5 text-[13px] font-bold text-n-700 no-underline hover:bg-n-50"
        >
          Voltar ao início
        </a>
      </div>
    </main>
  );
}
