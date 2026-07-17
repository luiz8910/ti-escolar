"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  atualizarStatusSolicitacaoInterna,
  CategoriaSolicitacao,
  getSessao,
  listarSolicitacoesInternas,
  logout,
  removerSolicitacaoInterna,
  responderSolicitacaoInterna,
  SolicitacaoInterna,
  StatusSolicitacaoInterna,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/form";
import { Badge } from "@/components/ui/Badge";
import { useToast } from "@/components/ui/Toast";

const CATEGORIA_LABEL: Record<CategoriaSolicitacao, string> = {
  secretaria: "Secretaria",
  gestao: "Gestão",
  pedagogico: "Pedagógico",
};
const CATEGORIA_TONE: Record<CategoriaSolicitacao, "neutral" | "brand" | "success"> = {
  secretaria: "brand",
  gestao: "neutral",
  pedagogico: "success",
};

const STATUS_LABEL: Record<StatusSolicitacaoInterna, string> = {
  aberta: "Aberta",
  em_andamento: "Em andamento",
  resolvida: "Resolvida",
  cancelada: "Cancelada",
};
const STATUS_TONE: Record<
  StatusSolicitacaoInterna,
  "neutral" | "brand" | "success" | "danger"
> = {
  aberta: "brand",
  em_andamento: "neutral",
  resolvida: "success",
  cancelada: "danger",
};

export default function CanalDoProfessor() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [itens, setItens] = useState<SolicitacaoInterna[]>([]);
  const [categoria, setCategoria] = useState<CategoriaSolicitacao | "">("");
  const [status, setStatus] = useState<StatusSolicitacaoInterna | "">("");
  const toast = useToast();

  const recarregar = useCallback(async () => {
    const dados = await listarSolicitacoesInternas({
      categoria: categoria || undefined,
      status: status || undefined,
    });
    setItens(dados);
  }, [categoria, status]);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    recarregar().catch(() =>
      toast({ tone: "danger", title: "Falha ao carregar o canal." })
    );
  }, [router, recarregar, toast]);

  async function mudarStatus(id: string, novo: StatusSolicitacaoInterna) {
    try {
      await atualizarStatusSolicitacaoInterna(id, novo);
      await recarregar();
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha." });
    }
  }

  async function remover(id: string) {
    try {
      await removerSolicitacaoInterna(id);
      await recarregar();
      toast({ tone: "success", title: "Solicitação removida." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha." });
    }
  }

  if (!usuario) return null;

  return (
    <AppShell
      title="Canal do professor"
      user={{
        name: usuario.nome,
        role: usuario.papel === "super_admin" ? "Super Admin" : "Admin da escola",
      }}
      tenantName="Escola Demonstração"
      isSuperAdmin={usuario.papel === "super_admin"}
      onLogout={() => {
        logout();
        router.replace("/admin/login");
      }}
    >
      <div className="flex flex-col gap-[18px]">
        <Card>
          <CardHeader
            title={`Solicitações (${itens.length})`}
            action={
              <div className="flex flex-wrap gap-2">
                <Select
                  className="w-40"
                  value={categoria}
                  onChange={(e) =>
                    setCategoria(e.target.value as CategoriaSolicitacao | "")
                  }
                >
                  <option value="">Todas as áreas</option>
                  <option value="secretaria">Secretaria</option>
                  <option value="gestao">Gestão</option>
                  <option value="pedagogico">Pedagógico</option>
                </Select>
                <Select
                  className="w-40"
                  value={status}
                  onChange={(e) =>
                    setStatus(e.target.value as StatusSolicitacaoInterna | "")
                  }
                >
                  <option value="">Todos os status</option>
                  <option value="aberta">Abertas</option>
                  <option value="em_andamento">Em andamento</option>
                  <option value="resolvida">Resolvidas</option>
                  <option value="cancelada">Canceladas</option>
                </Select>
              </div>
            }
          />
          <p className="mb-3 text-sm text-n-500">
            Recados e pedidos que os professores enviam pelo sistema — registrados e
            roteados por área, sem depender do WhatsApp pessoal.
          </p>
          {itens.length === 0 ? (
            <p className="text-sm text-n-500">Nenhuma solicitação no filtro atual.</p>
          ) : (
            <div className="flex flex-col gap-3">
              {itens.map((s) => (
                <ItemSolicitacao
                  key={s.id}
                  item={s}
                  onStatus={mudarStatus}
                  onRemover={remover}
                  onRecarregar={recarregar}
                />
              ))}
            </div>
          )}
        </Card>
      </div>
    </AppShell>
  );
}

function ItemSolicitacao({
  item,
  onStatus,
  onRemover,
  onRecarregar,
}: {
  item: SolicitacaoInterna;
  onStatus: (id: string, s: StatusSolicitacaoInterna) => Promise<void>;
  onRemover: (id: string) => Promise<void>;
  onRecarregar: () => Promise<void>;
}) {
  const toast = useToast();
  const [resposta, setResposta] = useState(item.resposta);
  const [notificar, setNotificar] = useState(false);
  const [respondendo, setRespondendo] = useState(false);

  async function responder(e: React.FormEvent) {
    e.preventDefault();
    if (!resposta.trim()) return;
    try {
      await responderSolicitacaoInterna(item.id, resposta.trim(), notificar);
      setRespondendo(false);
      await onRecarregar();
      toast({ tone: "success", title: "Resposta registrada." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha." });
    }
  }

  return (
    <div className="rounded-[12px] border border-n-100 p-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-n-900">{item.assunto}</span>
        <Badge tone={CATEGORIA_TONE[item.categoria]}>
          {CATEGORIA_LABEL[item.categoria]}
        </Badge>
        <Badge tone={STATUS_TONE[item.status]}>{STATUS_LABEL[item.status]}</Badge>
        <span className="ml-auto text-xs text-n-400">
          {item.professor_nome || "—"}
        </span>
      </div>
      <p className="mt-1.5 whitespace-pre-wrap text-sm text-n-700">{item.corpo}</p>

      {item.resposta && (
        <div className="mt-2 rounded-[10px] bg-n-50 p-2.5 text-sm text-n-700">
          <span className="text-xs font-bold text-n-500">Resposta da escola:</span>
          <p className="mt-0.5 whitespace-pre-wrap">{item.resposta}</p>
        </div>
      )}

      {respondendo ? (
        <form onSubmit={responder} className="mt-2.5 flex flex-col gap-2">
          <Input
            value={resposta}
            onChange={(e) => setResposta(e.target.value)}
            placeholder="Resposta ao professor"
          />
          <label className="flex items-center gap-2 text-sm text-n-600">
            <input
              type="checkbox"
              checked={notificar}
              onChange={(e) => setNotificar(e.target.checked)}
            />
            Avisar o professor por WhatsApp
          </label>
          <div className="flex gap-1.5">
            <Button size="sm" type="submit">
              Enviar resposta
            </Button>
            <Button
              size="sm"
              variant="secondary"
              type="button"
              onClick={() => setRespondendo(false)}
            >
              Cancelar
            </Button>
          </div>
        </form>
      ) : (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          <Button size="sm" onClick={() => setRespondendo(true)}>
            Responder
          </Button>
          {item.status === "aberta" && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => onStatus(item.id, "em_andamento")}
            >
              Em andamento
            </Button>
          )}
          {item.status !== "cancelada" && item.status !== "resolvida" && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => onStatus(item.id, "cancelada")}
            >
              Cancelar
            </Button>
          )}
          <Button size="sm" variant="danger" onClick={() => onRemover(item.id)}>
            Excluir
          </Button>
        </div>
      )}
    </div>
  );
}
