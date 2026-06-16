"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { getSessao, logout, obterPrompt, salvarPrompt, Usuario } from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";
import { InstructionsIcon } from "@/components/ui/icons";

const EXEMPLO =
  "Ex.: Trate os responsáveis pelo primeiro nome. Reforce o uso obrigatório do uniforme. " +
  "Para assuntos formais, oriente o e-mail secretaria@escola.test. Nunca compartilhe notas " +
  "de um aluno com quem não seja o responsável cadastrado.";

export default function InstrucoesDaEscola() {
  const router = useRouter();
  const toast = useToast();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [conteudo, setConteudo] = useState("");
  const [atualizadoEm, setAtualizadoEm] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

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
    carregar().catch(() => toast({ tone: "danger", title: "Falha ao carregar as instruções." }));
  }, [router, carregar, toast]);

  function sair() {
    logout();
    router.replace("/admin/login");
  }

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    setSalvando(true);
    try {
      const p = await salvarPrompt(conteudo);
      setAtualizadoEm(p.atualizado_em);
      toast({
        tone: "success",
        title: "Instruções salvas.",
        description: "O assistente já as utilizará nas próximas conversas.",
      });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao salvar." });
    } finally {
      setSalvando(false);
    }
  }

  if (!usuario) return null;

  return (
    <AppShell
      title="Instruções da escola"
      user={{
        name: usuario.nome,
        role: usuario.papel === "super_admin" ? "Super Admin" : "Admin da escola",
      }}
      tenantName="Escola Demonstração"
      isSuperAdmin={usuario.papel === "super_admin"}
      onLogout={sair}
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-[18px]">
        <div className="flex items-start gap-3 rounded-lg border border-accent/30 bg-accent-soft px-4 py-3.5 text-[13px] text-[#7a5208]">
          <InstructionsIcon size={18} className="mt-0.5 flex-none text-accent" />
          <p>
            Estas instruções funcionam como um <b>&ldquo;CLAUDE.md&rdquo; da sua escola</b>: são
            anexadas às diretrizes do assistente e têm prioridade institucional. Use para ajustar
            tom, regras de privacidade e contexto específico deste tenant.
          </p>
        </div>

        <Card>
          <form onSubmit={salvar} className="flex flex-col gap-3">
            <Textarea
              value={conteudo}
              onChange={(e) => setConteudo(e.target.value)}
              placeholder={EXEMPLO}
              rows={14}
            />
            <div className="flex items-center justify-between border-t border-n-100 pt-3.5">
              <span className="text-xs text-n-400">
                {atualizadoEm
                  ? `Atualizado em ${new Date(atualizadoEm).toLocaleString("pt-BR")}`
                  : "Ainda não definido"}
              </span>
              <Button type="submit" loading={salvando}>
                {salvando ? "Salvando…" : "Salvar instruções"}
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </AppShell>
  );
}
