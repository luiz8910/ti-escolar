"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { login } from "@/lib/admin";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);

  async function entrar(e: React.FormEvent) {
    e.preventDefault();
    setErro("");
    setCarregando(true);
    try {
      await login(email.trim(), senha);
      router.push("/admin");
    } catch {
      setErro("E-mail ou senha inválidos.");
    } finally {
      setCarregando(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <div className="w-full max-w-sm rounded-xl bg-white p-8 shadow-lg">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-wa-header text-2xl">
            🎓
          </div>
          <h1 className="text-lg font-semibold text-slate-800">TI-Escolar — Admin</h1>
          <p className="text-sm text-slate-500">Painel administrativo</p>
        </div>

        <form onSubmit={entrar} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">E-mail</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-wa-header"
              placeholder="admin@escola-demo.test"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Senha</label>
            <input
              type="password"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              required
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-wa-header"
              placeholder="••••••••"
            />
          </div>

          {erro && <p className="text-sm text-red-600">{erro}</p>}

          <button
            type="submit"
            disabled={carregando}
            className="w-full rounded-lg bg-wa-header py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {carregando ? "Entrando…" : "Entrar"}
          </button>
        </form>

        <div className="mt-6 rounded-lg bg-slate-50 p-3 text-xs text-slate-500">
          <p className="font-medium text-slate-600">Credenciais de demonstração:</p>
          <p>Super admin: admin@tiescolar.test / troque-esta-senha</p>
          <p>Admin escola: admin@escola-demo.test / escola123</p>
        </div>
      </div>
    </main>
  );
}
