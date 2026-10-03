"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  BroadcastDetalhe,
  BroadcastResumo,
  cancelarBroadcast,
  exigeEscolhaDeEscola,
  getSessao,
  listarBroadcasts,
  logout,
  obterBroadcast,
  renomearBroadcast,
  tenantEmFoco,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/form";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableWrap, Table, Th, Td, Tr } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";
import {
  Paginacao,
  salvarTamanhoPreferido,
  tamanhoPreferido,
  type PaginaMeta,
} from "@/components/ui/Paginacao";
import { cn } from "@/components/ui/cn";
import { BellIcon, PencilIcon, XCircleIcon } from "@/components/ui/icons";

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
  cancelado: "Cancelado",
};

const TONE_BROADCAST: Record<string, "neutral" | "brand" | "success" | "warning"> = {
  rascunho: "neutral",
  agendado: "brand",
  em_envio: "brand",
  concluido: "success",
  parcial_limite: "warning",
  cancelado: "neutral",
};

// Só estes ainda têm mensagem por enviar — e, portanto, algo para cancelar. Disparo
// concluído não se apaga: é o registro de que a escola avisou, e de quem recebeu.
const STATUS_CANCELAVEIS = ["em_envio", "parcial_limite", "agendado"];

// Status de entrega por destinatário (vocabulário da Meta).
const ROTULO_ENTREGA: Record<string, string> = {
  pendente: "Pendente",
  enfileirado: "Enfileirado",
  sent: "Enviado",
  delivered: "Entregue",
  read: "Lido",
  failed: "Falhou",
  cancelado: "Cancelado",
};

const TONE_ENTREGA: Record<string, "neutral" | "brand" | "success" | "warning" | "danger"> = {
  pendente: "neutral",
  enfileirado: "neutral",
  sent: "brand",
  delivered: "success",
  read: "success",
  failed: "danger",
  cancelado: "neutral",
};

export default function HistoricoDisparos() {
  const router = useRouter();
  const toast = useToast();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [broadcasts, setBroadcasts] = useState<BroadcastResumo[]>([]);
  const [carregando, setCarregando] = useState(true);

  const [meta, setMeta] = useState<PaginaMeta | null>(null);
  const [pagina, setPagina] = useState(1);
  const [porPagina, setPorPagina] = useState(() => tamanhoPreferido("disparos"));

  const recarregar = useCallback(async () => {
    const resultado = await listarBroadcasts(tenantEmFoco(), pagina, porPagina);
    setBroadcasts(resultado.itens);
    setMeta(resultado.meta);
  }, [pagina, porPagina]);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    // Super admin sem escola escolhida: a AppShell mostra o pedido de escolha e
    // nenhuma busca é disparada — `tenantEmFoco()` lançaria, e antes desta guarda o
    // painel simplesmente operava sobre a escola de demonstração.
    if (exigeEscolhaDeEscola()) return;
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
          <Disparos
            broadcasts={broadcasts}
            meta={meta}
            onPagina={setPagina}
            onMudou={recarregar}
            onTamanho={(t) => {
              salvarTamanhoPreferido("disparos", t);
              setPorPagina(t);
              setPagina(1);
            }}
          />
        )}
      </div>
    </AppShell>
  );
}

function Disparos({
  broadcasts,
  meta,
  onPagina,
  onTamanho,
  onMudou,
}: {
  broadcasts: BroadcastResumo[];
  meta: PaginaMeta | null;
  onPagina: (p: number) => void;
  onTamanho: (t: number) => void;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [aberto, setAberto] = useState<BroadcastDetalhe | null>(null);
  const [carregandoId, setCarregandoId] = useState<string | null>(null);
  const [renomeando, setRenomeando] = useState(false);
  const [cancelando, setCancelando] = useState(false);

  async function confirmarCancelamento() {
    if (!aberto) return;
    const alvo = aberto;
    setCancelando(false);
    try {
      const r = await cancelarBroadcast(tenantEmFoco(), alvo.id);
      toast({
        tone: "success",
        title: "Disparo cancelado.",
        description: r.em_envio
          ? "O envio em curso para na próxima mensagem. Atualize para ver quem chegou a receber."
          : `${r.cancelados} destinatário(s) ainda aguardavam e não vão receber.`,
      });
    } catch (err) {
      // 409 = terminou antes do clique. A tela é recarregada de qualquer jeito, para
      // mostrar o estado real em vez do que estava aberto.
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao cancelar o disparo.",
      });
    }
    await onMudou().catch(() => undefined);
    await abrir(alvo.id);
  }

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
        {meta && (
          <Paginacao
            meta={meta}
            onPagina={onPagina}
            onTamanho={onTamanho}
            rotulo="disparo(s)"
          />
        )}
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
          <DetalheDisparo
            detalhe={aberto}
            onRenomear={() => setRenomeando(true)}
            onCancelar={() => setCancelando(true)}
          />
        )}
      </Card>

      {renomeando && aberto && (
        <RenomearDisparoModal
          detalhe={aberto}
          onClose={() => setRenomeando(false)}
          onSalvo={async (titulo) => {
            setAberto({ ...aberto, titulo });
            await onMudou();
          }}
        />
      )}

      <ConfirmDialog
        open={cancelando && aberto !== null}
        onClose={() => setCancelando(false)}
        onConfirm={confirmarCancelamento}
        title="Cancelar disparo"
        confirmLabel="Cancelar disparo"
        cancelLabel="Voltar"
        message={
          aberto
            ? `“${aberto.titulo}” para de ser enviado: quem ainda não recebeu não vai mais ` +
              `receber, nem agora nem na retomada. Quem já recebeu continua no histórico — ` +
              `mensagem entregue não tem como ser desfeita. O cancelamento não pode ser revertido.`
            : ""
        }
      />
    </div>
  );
}

function RenomearDisparoModal({
  detalhe,
  onClose,
  onSalvo,
}: {
  detalhe: BroadcastDetalhe;
  onClose: () => void;
  onSalvo: (titulo: string) => Promise<void>;
}) {
  const toast = useToast();
  const [titulo, setTitulo] = useState(detalhe.titulo);
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function salvar(e?: React.FormEvent) {
    e?.preventDefault();
    if (salvando) return;
    if (!titulo.trim()) {
      setErro("Informe o título do disparo.");
      return;
    }
    setSalvando(true);
    setErro("");
    try {
      await renomearBroadcast(tenantEmFoco(), detalhe.id, titulo.trim());
      onClose();
      await onSalvo(titulo.trim());
      toast({ tone: "success", title: "Título atualizado." });
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Falha ao renomear o disparo.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Renomear disparo"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancelar
          </Button>
          <Button size="sm" onClick={() => salvar()} loading={salvando}>
            Salvar
          </Button>
        </>
      }
    >
      <form onSubmit={salvar} className="flex flex-col gap-3">
        <Field
          label="Título"
          htmlFor="disparo-titulo"
          hint="Só o rótulo do histórico. O texto enviado aos responsáveis não muda."
        >
          <Input
            id="disparo-titulo"
            value={titulo}
            maxLength={300}
            onChange={(e) => setTitulo(e.target.value)}
            autoFocus
          />
        </Field>
        {erro && (
          <p className="rounded-lg bg-danger-soft px-3 py-2 text-[12.5px] text-danger">{erro}</p>
        )}
        <button type="submit" className="hidden" aria-hidden tabIndex={-1} />
      </form>
    </Modal>
  );
}

function DetalheDisparo({
  detalhe,
  onRenomear,
  onCancelar,
}: {
  detalhe: BroadcastDetalhe;
  onRenomear: () => void;
  onCancelar: () => void;
}) {
  const cancelavel = STATUS_CANCELAVEIS.includes(detalhe.status);
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
        <div className="flex flex-wrap items-center justify-end gap-1.5">
          <Badge tone={TONE_BROADCAST[detalhe.status] ?? "neutral"}>
            {ROTULO_BROADCAST[detalhe.status] ?? detalhe.status}
          </Badge>
          <Button
            size="sm"
            variant="secondary"
            leftIcon={<PencilIcon size={14} />}
            onClick={onRenomear}
          >
            Renomear
          </Button>
          {/* Só aparece enquanto há o que interromper: num disparo concluído o botão
              prometeria desfazer uma mensagem que já está no WhatsApp dos pais. */}
          {cancelavel && (
            <Button
              size="sm"
              variant="danger"
              leftIcon={<XCircleIcon size={14} />}
              onClick={onCancelar}
            >
              Cancelar disparo
            </Button>
          )}
        </div>
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
                  {d.erro && (
                    // O motivo, na palavra da Meta. Sem ele a tela dizia só "Falhou" e a
                    // causa não existia em lugar nenhum.
                    <p className="mt-1 max-w-[420px] text-[11px] leading-snug text-danger">
                      {d.erro}
                    </p>
                  )}
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
