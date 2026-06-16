"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { login } from "@/lib/admin";
import { Field, Input } from "@/components/ui/form";
import { Button } from "@/components/ui/Button";
import { ChatBubbleIcon } from "@/components/ui/icons";

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
    <main className="grid min-h-screen lg:grid-cols-2">
      {/* Painel de marca */}
      <aside className="relative hidden flex-col justify-between bg-gradient-to-br from-brand-900 to-brand-600 p-12 text-white lg:flex">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/15">
            <ChatBubbleIcon size={20} />
          </div>
          <span className="text-lg font-extrabold tracking-tight">
            TI<span className="text-white/60">·</span>Escolar
          </span>
        </div>

        <div className="max-w-md">
          <h1 className="text-3xl font-extrabold leading-tight tracking-tight">
            A comunicação da sua escola, no WhatsApp.
          </h1>
          <p className="mt-4 text-[15px] leading-relaxed text-white/75">
            Avisos para pais, base de conhecimento e atendimento automático —
            tudo em um painel só, com cota e templates da Meta sob controle.
          </p>
        </div>

        <p className="text-xs text-white/50">© TI-Escolar · Painel administrativo</p>
      </aside>

      {/* Formulário */}
      <div className="flex items-center justify-center bg-bg p-6">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <div className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-brand-600 text-white">
              <ChatBubbleIcon size={18} />
            </div>
            <span className="text-lg font-extrabold tracking-tight text-n-900">
              TI<span className="text-brand-600">·</span>Escolar
            </span>
          </div>

          <h2 className="text-xl font-bold tracking-tight text-n-900">Entrar no painel</h2>
          <p className="mt-1 text-sm text-n-500">Acesse com as credenciais da escola.</p>

          <form onSubmit={entrar} className="mt-6 flex flex-col gap-4">
            <Field label="E-mail" htmlFor="email">
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="admin@escola-demo.test"
              />
            </Field>
            <Field label="Senha" htmlFor="senha" error={erro || undefined}>
              <Input
                id="senha"
                type="password"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                required
                placeholder="••••••••"
                invalid={!!erro}
              />
            </Field>

            <Button type="submit" loading={carregando} className="mt-1 w-full">
              {carregando ? "Entrando…" : "Entrar"}
            </Button>
          </form>

          <div className="mt-7 rounded-lg border border-n-200 bg-n-50 p-3.5 text-xs text-n-500">
            <p className="mb-1 font-bold text-n-600">Credenciais de demonstração</p>
            <p className="font-mono text-[11.5px]">
              Super admin: admin@tiescolar.test / troque-esta-senha
            </p>
            <p className="font-mono text-[11.5px]">
              Admin escola: admin@escola-demo.test / escola123
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
