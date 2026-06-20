"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  BroadcastDetalhe,
  BroadcastResumo,
  getSessao,
  listarBroadcasts,
  logout,
  obterBroadcast,
  tenantEmFoco,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableWrap, Table, Th, Td, Tr } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/components/ui/cn";
import { BellIcon } from "@/components/ui/icons";

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

const ROTULO_BROADCAST: Record<string, string> = {
  rascunho: "Rascunho",
  agendado: "Agendado",
  em_envio: "Em envio",
  concluido: "Concluído",
  parcial_limite: "Parcial (cota)",
};

const TONE_BROADCAST: Record<string, "neutral" | "brand" | "success" | "warning"> = {
  rascunho: "neutral",
  agendado: "brand",
  em_envio: "brand",
  concluido: "success",
  parcial_limite: "warning",
};

// Status de entrega por destinatário (vocabulário da Meta).
const ROTULO_ENTREGA: Record<string, string> = {
  pendente: "Pendente",
  enfileirado: "Enfileirado",
  sent: "Enviado",
  delivered: "Entregue",
  read: "Lido",
  failed: "Falhou",
};

const TONE_ENTREGA: Record<string, "neutral" | "brand" | "success" | "warning" | "danger"> = {
  pendente: "neutral",
  enfileirado: "neutral",
  sent: "brand",
  delivered: "success",
  read: "success",
  failed: "danger",
};

export default function HistoricoDisparos() {
  const router = useRouter();
  const toast = useToast();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [broadcasts, setBroadcasts] = useState<BroadcastResumo[]>([]);
  const [carregando, setCarregando] = useState(true);

  const recarregar = useCallback(async () => {
    setBroadcasts(await listarBroadcasts(tenantEmFoco()));
  }, []);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    recarregar()
      .catch(() => toast({ tone: "danger", title: "Falha ao carregar os disparos." }))
      .finally(() => setCarregando(false));
  }, [router, recarregar, toast]);

  function sair() {
    logout();
    router.replace("/admin/login");
  }

  if (!usuario) return null;

  return (
    <AppShell
      title="Histórico de mensagens em massa"
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
          <BellIcon size={18} className="mt-0.5 flex-none text-brand-600" />
          <p>
            Todos os disparos enviados aos responsáveis — com <b>template</b>, número de
            destinatários, <b>status de entrega</b> e data. Clique em um disparo para ver a entrega
            por responsável.
          </p>
        </div>

        {carregando ? (
          <p className="text-sm text-n-400">Carregando…</p>
        ) : (
          <Disparos broadcasts={broadcasts} />
        )}
      </div>
    </AppShell>
  );
}

function Disparos({ broadcasts }: { broadcasts: BroadcastResumo[] }) {
  const toast = useToast();
  const [aberto, setAberto] = useState<BroadcastDetalhe | null>(null);
  const [carregandoId, setCarregandoId] = useState<string | null>(null);

  async function abrir(id: string) {
    setCarregandoId(id);
    try {
      setAberto(await obterBroadcast(tenantEmFoco(), id));
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao abrir o disparo.",
      });
    } finally {
      setCarregandoId(null);
    }
  }

  if (broadcasts.length === 0) {
    return (
      <Card className="flex items-center justify-center py-10">
        <EmptyState
          icon={<BellIcon size={24} />}
          title="Nenhuma mensagem em massa"
          description="Esta escola ainda não enviou nenhum disparo para os responsáveis."
        />
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-[18px] lg:grid-cols-[360px_1fr]">
      <Card className="p-3">
        <div className="flex flex-col gap-1">
          {broadcasts.map((b) => {
            const active = aberto?.id === b.id;
            return (
              <button
                key={b.id}
                onClick={() => abrir(b.id)}
                className={cn(
                  "w-full rounded-[10px] px-3 py-2.5 text-left",
                  active ? "bg-brand-600 text-white" : "hover:bg-n-50"
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[13px] font-semibold">{b.titulo}</span>
                  <span
                    className={cn(
                      "flex-none rounded-full px-2 py-0.5 text-[11px] font-bold",
                      active ? "bg-white/20" : "bg-n-100 text-n-500"
                    )}
                  >
                    {b.total_destinatarios}
                  </span>
                </div>
                <p className={cn("mt-0.5 text-xs", active ? "text-white/80" : "text-n-500")}>
                  {b.template_nome || "sem template"} · {ROTULO_BROADCAST[b.status] ?? b.status}
                </p>
                <p className={cn("text-[10px]", active ? "text-white/60" : "text-n-400")}>
                  {formatar(b.criado_em)}
                </p>
              </button>
            );
          })}
        </div>
      </Card>

      <Card>
        {carregandoId ? (
          <p className="text-sm text-n-400">Carregando disparo…</p>
        ) : !aberto ? (
          <div className="flex h-full items-center justify-center">
            <EmptyState
              icon={<BellIcon size={24} />}
              title="Selecione um disparo"
              description="Escolha um disparo à esquerda para ver o template e a entrega por responsável."
            />
          </div>
        ) : (
          <DetalheDisparo detalhe={aberto} />
        )}
      </Card>
    </div>
  );
}

function DetalheDisparo({ detalhe }: { detalhe: BroadcastDetalhe }) {
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-2 border-b border-n-100 pb-3">
        <div>
          <h2 className="text-sm font-bold text-n-900">{detalhe.titulo}</h2>
          <p className="text-xs text-n-400">
            {detalhe.template_nome ? (
              <>
                Template <b>{detalhe.template_nome}</b> ·{" "}
              </>
            ) : null}
            {formatar(detalhe.criado_em)} · {detalhe.total_destinatarios} destinatário(s)
          </p>
        </div>
        <Badge tone={TONE_BROADCAST[detalhe.status] ?? "neutral"}>
          {ROTULO_BROADCAST[detalhe.status] ?? detalhe.status}
        </Badge>
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        {Object.entries(detalhe.por_status).map(([st, n]) => (
          <Badge key={st} tone={TONE_ENTREGA[st] ?? "neutral"}>
            {ROTULO_ENTREGA[st] ?? st}: {n}
          </Badge>
        ))}
      </div>

      <TableWrap>
        <Table>
          <thead>
            <tr>
              <Th>Responsável</Th>
              <Th>WhatsApp</Th>
              <Th>Entrega</Th>
              <Th>Atualizado</Th>
            </tr>
          </thead>
          <tbody>
            {detalhe.destinatarios.map((d) => (
              <Tr key={d.contato}>
                <Td className="font-medium">{d.nome || "—"}</Td>
                <Td className="font-mono text-xs text-n-500">{d.contato}</Td>
                <Td>
                  <Badge tone={TONE_ENTREGA[d.status] ?? "neutral"}>
                    {ROTULO_ENTREGA[d.status] ?? d.status}
                  </Badge>
                </Td>
                <Td className="text-xs text-n-500">{formatar(d.atualizado_em)}</Td>
              </Tr>
            ))}
            {detalhe.destinatarios.length === 0 && (
              <Tr>
                <Td colSpan={4} className="text-n-400">
                  Sem destinatários.
                </Td>
              </Tr>
            )}
          </tbody>
        </Table>
      </TableWrap>
    </div>
  );
}
