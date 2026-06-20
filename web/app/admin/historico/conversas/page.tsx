"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  ConversaDetalhe,
  ConversaResumo,
  getSessao,
  listarConversas,
  logout,
  obterConversa,
  tenantEmFoco,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/components/ui/cn";
import { ChatBubbleIcon } from "@/components/ui/icons";

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

export default function HistoricoConversas() {
  const router = useRouter();
  const toast = useToast();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [conversas, setConversas] = useState<ConversaResumo[]>([]);
  const [carregando, setCarregando] = useState(true);

  const recarregar = useCallback(async () => {
    setConversas(await listarConversas(tenantEmFoco()));
  }, []);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    recarregar()
      .catch(() => toast({ tone: "danger", title: "Falha ao carregar conversas." }))
      .finally(() => setCarregando(false));
  }, [router, recarregar, toast]);

  function sair() {
    logout();
    router.replace("/admin/login");
  }

  if (!usuario) return null;

  return (
    <AppShell
      title="Histórico de conversas"
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
          <ChatBubbleIcon size={18} className="mt-0.5 flex-none text-brand-600" />
          <p>
            Histórico das conversas no WhatsApp entre os responsáveis e o assistente — todas as
            mensagens <b>recebidas</b> e as <b>respostas da IA</b>, com as fontes citadas.
          </p>
        </div>

        {carregando ? (
          <p className="text-sm text-n-400">Carregando…</p>
        ) : (
          <Conversas conversas={conversas} />
        )}
      </div>
    </AppShell>
  );
}

function Conversas({ conversas }: { conversas: ConversaResumo[] }) {
  const toast = useToast();
  const [aberta, setAberta] = useState<ConversaDetalhe | null>(null);
  const [carregandoId, setCarregandoId] = useState<string | null>(null);

  async function abrir(id: string) {
    setCarregandoId(id);
    try {
      setAberta(await obterConversa(tenantEmFoco(), id));
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao abrir conversa.",
      });
    } finally {
      setCarregandoId(null);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-[18px] lg:grid-cols-[300px_1fr]">
      <Card className="p-3">
        {conversas.length === 0 ? (
          <p className="p-3 text-sm text-n-400">Nenhuma conversa iniciada pelos pais ainda.</p>
        ) : (
          <div className="flex flex-col gap-1">
            {conversas.map((c) => {
              const active = aberta?.id === c.id;
              return (
                <button
                  key={c.id}
                  onClick={() => abrir(c.id)}
                  className={cn(
                    "w-full rounded-[10px] px-3 py-2.5 text-left",
                    active ? "bg-brand-600 text-white" : "hover:bg-n-50"
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[13px] font-semibold">{c.contato}</span>
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-[11px] font-bold",
                        active ? "bg-white/20" : "bg-n-100 text-n-500"
                      )}
                    >
                      {c.total_mensagens}
                    </span>
                  </div>
                  <p className={cn("mt-0.5 truncate text-xs", active ? "text-white/80" : "text-n-500")}>
                    {c.ultima_mensagem || "sem mensagens"}
                  </p>
                  <p className={cn("text-[10px]", active ? "text-white/60" : "text-n-400")}>
                    {formatar(c.ultima_em ?? c.criado_em)}
                  </p>
                </button>
              );
            })}
          </div>
        )}
      </Card>

      <Card>
        {carregandoId ? (
          <p className="text-sm text-n-400">Carregando conversa…</p>
        ) : !aberta ? (
          <div className="flex h-full items-center justify-center">
            <EmptyState
              icon={<ChatBubbleIcon size={24} />}
              title="Selecione uma conversa"
              description="Escolha uma conversa à esquerda para ver as mensagens trocadas com a IA."
            />
          </div>
        ) : (
          <div>
            <div className="mb-4 border-b border-n-100 pb-3">
              <h2 className="text-sm font-bold text-n-900">{aberta.contato}</h2>
              <p className="text-xs text-n-400">
                Iniciada em {formatar(aberta.criado_em)} · {aberta.mensagens.length} mensagens
              </p>
            </div>
            <div className="flex flex-col gap-2">
              {aberta.mensagens.map((m) => (
                <div
                  key={m.id}
                  className={cn("flex", m.autor === "usuario" ? "justify-end" : "justify-start")}
                >
                  <div
                    className={cn(
                      "max-w-[80%] rounded-2xl px-3.5 py-2.5 text-[13px]",
                      m.autor === "usuario" ? "bg-brand-50 text-n-900" : "bg-n-100 text-n-900"
                    )}
                  >
                    <p className="whitespace-pre-wrap leading-relaxed">{m.texto}</p>
                    {m.fontes.length > 0 && (
                      <p className="mt-1 text-[10px] text-n-500">Fontes: {m.fontes.join(", ")}</p>
                    )}
                    <p className="mt-1 text-right text-[10px] text-n-400">{formatar(m.criado_em)}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
