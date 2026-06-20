"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  getSessao,
  listarAuditoria,
  logout,
  RegistroAuditoria,
  tenantEmFoco,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/components/ui/cn";
import { FileIcon, SparkIcon, UsersIcon } from "@/components/ui/icons";

function formatar(data: string | null): string {
  if (!data) return "—";
  return new Date(data).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const ATOR: Record<
  RegistroAuditoria["ator"],
  { rotulo: string; tone: "brand" | "success" | "neutral" }
> = {
  usuario: { rotulo: "Usuário", tone: "brand" },
  llm: { rotulo: "Assistente (IA)", tone: "success" },
  sistema: { rotulo: "Sistema", tone: "neutral" },
};

export default function HistoricoAuditoria() {
  const router = useRouter();
  const toast = useToast();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [registros, setRegistros] = useState<RegistroAuditoria[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [filtro, setFiltro] = useState<"todos" | "usuario" | "llm">("todos");

  const recarregar = useCallback(async () => {
    setRegistros(await listarAuditoria(tenantEmFoco()));
  }, []);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    recarregar()
      .catch(() => toast({ tone: "danger", title: "Falha ao carregar a auditoria." }))
      .finally(() => setCarregando(false));
  }, [router, recarregar, toast]);

  function sair() {
    logout();
    router.replace("/admin/login");
  }

  if (!usuario) return null;

  const filtrados =
    filtro === "todos" ? registros : registros.filter((r) => r.ator === filtro);

  return (
    <AppShell
      title="Auditoria de ações"
      user={{
        name: usuario.nome,
        role: usuario.papel === "super_admin" ? "Super Admin" : "Admin da escola",
      }}
      tenantName="Escola Demonstração"
      isSuperAdmin={usuario.papel === "super_admin"}
      onLogout={sair}
    >
      <div className="flex flex-col gap-[18px]">
        <div className="flex items-start gap-3 rounded-lg border border-brand-200 bg-brand-50 px-4 py-3.5 text-[13px] text-brand-900">
          <FileIcon size={18} className="mt-0.5 flex-none text-brand-600" />
          <p>
            Registro das ações feitas por <b>usuários logados</b> no painel e pelo{" "}
            <b>assistente (IA)</b> — quem, o quê e quando. Base para rastreabilidade e compliance.
          </p>
        </div>

        <div className="inline-flex w-fit gap-1 rounded-lg border border-n-200 bg-white p-1 shadow-sm">
          <Filtro active={filtro === "todos"} onClick={() => setFiltro("todos")}>
            Todos
            <span className="ml-1 text-n-400">{registros.length}</span>
          </Filtro>
          <Filtro active={filtro === "usuario"} onClick={() => setFiltro("usuario")}>
            <UsersIcon size={15} /> Usuários
          </Filtro>
          <Filtro active={filtro === "llm"} onClick={() => setFiltro("llm")}>
            <SparkIcon size={15} /> IA
          </Filtro>
        </div>

        {carregando ? (
          <p className="text-sm text-n-400">Carregando…</p>
        ) : filtrados.length === 0 ? (
          <Card className="flex items-center justify-center py-10">
            <EmptyState
              icon={<FileIcon size={24} />}
              title="Nenhuma ação registrada"
              description="As ações de usuários e do assistente aparecerão aqui conforme acontecem."
            />
          </Card>
        ) : (
          <Card className="p-0">
            <div className="flex flex-col">
              {filtrados.map((r) => (
                <Registro key={r.id} registro={r} />
              ))}
            </div>
          </Card>
        )}
      </div>
    </AppShell>
  );
}

function Filtro({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-3.5 py-2 text-[13px] font-semibold transition-colors",
        active ? "bg-brand-600 text-white" : "text-n-600 hover:bg-n-50"
      )}
    >
      {children}
    </button>
  );
}

function Registro({ registro }: { registro: RegistroAuditoria }) {
  const [aberto, setAberto] = useState(false);
  const ator = ATOR[registro.ator] ?? ATOR.sistema;
  const temMeta = registro.metadados && Object.keys(registro.metadados).length > 0;

  return (
    <div className="border-t border-n-100 px-5 py-3.5 first:border-t-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <Badge tone={ator.tone}>{ator.rotulo}</Badge>
          <span className="text-[13px] font-semibold text-n-900">{registro.descricao || registro.acao}</span>
        </div>
        <span className="font-mono text-[11px] text-n-400">{formatar(registro.criado_em)}</span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-n-500">
        {registro.ator_nome && <span>{registro.ator_nome}</span>}
        <span className="rounded bg-n-50 px-1.5 py-0.5 font-mono text-[10.5px] text-n-500">
          {registro.acao}
        </span>
        {temMeta && (
          <button
            onClick={() => setAberto((v) => !v)}
            className="font-semibold text-brand-600 hover:underline"
          >
            {aberto ? "ocultar detalhes" : "ver detalhes"}
          </button>
        )}
      </div>
      {aberto && temMeta && (
        <pre className="mt-2 overflow-x-auto rounded-md bg-n-50 p-3 text-[11px] leading-relaxed text-n-600">
          {JSON.stringify(registro.metadados, null, 2)}
        </pre>
      )}
    </div>
  );
}
