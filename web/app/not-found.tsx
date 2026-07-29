"use client";

/** 404 do painel — sem este arquivo, o Next serve a página preta padrão dele. */

import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-[70vh] flex-col items-center justify-center px-6 text-center">
      <div className="text-[46px] font-extrabold leading-none text-brand-600">404</div>
      <h1 className="mt-3 text-[19px] font-extrabold text-n-900">Página não encontrada</h1>
      <p className="mt-2 max-w-[380px] text-[13.5px] leading-relaxed text-n-500">
        O endereço não existe ou o item foi removido.
      </p>
      <Link
        href="/admin"
        className="mt-6 rounded-[10px] bg-brand-600 px-4 py-2.5 text-[13px] font-bold text-white no-underline hover:bg-brand-700"
      >
        Ir para o painel
      </Link>
    </main>
  );
}
