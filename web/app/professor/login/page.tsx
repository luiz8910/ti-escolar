"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getSessaoProfessor, loginProfessor } from "@/lib/professor";

import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";

export default function LoginProfessor() {
  const router = useRouter();
  const toast = useToast();
  const [telefone, setTelefone] = useState("");
  const [senha, setSenha] = useState("");
  const [carregando, setCarregando] = useState(false);

  useEffect(() => {
    if (getSessaoProfessor()) router.replace("/professor");
  }, [router]);

  async function entrar(e: React.FormEvent) {
    e.preventDefault();
    if (!telefone.trim() || !senha) return;
    setCarregando(true);
    try {
      await loginProfessor(telefone.trim(), senha);
      router.replace("/professor");
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha no login." });
    } finally {
      setCarregando(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-n-50 p-4">
      <div className="w-full max-w-sm">
        <div className="mb-5 text-center">
          <div className="text-lg font-extrabold tracking-tight text-n-900">
            TI<span className="text-brand-600">·</span>Escolar
          </div>
          <div className="mt-1 text-sm text-n-500">Mural do professor</div>
        </div>
        <Card>
          <CardHeader title="Entrar" />
          <form onSubmit={entrar} className="flex flex-col gap-3">
            <Input
              value={telefone}
              onChange={(e) => setTelefone(e.target.value)}
              placeholder="WhatsApp, ex.: +5511999990000"
            />
            <Input
              type="password"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              placeholder="Senha"
            />
            <Button type="submit" disabled={carregando}>
              {carregando ? "Entrando..." : "Entrar"}
            </Button>
          </form>
          <p className="mt-3 text-xs text-n-400">
            A senha é definida pela secretaria no cadastro de professores.
          </p>
        </Card>
      </div>
    </div>
  );
}
