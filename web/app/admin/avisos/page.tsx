"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  atualizarAviso,
  AvisoTemporizado,
  criarAviso,
  getSessao,
  listarAvisos,
  logout,
  removerAviso,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/form";
import { TableWrap, Table, Th, Td, Tr } from "@/components/ui/Table";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { Badge } from "@/components/ui/Badge";
import { useToast } from "@/components/ui/Toast";
import { PlusIcon } from "@/components/ui/icons";

// datetime-local (sem timezone) <-> ISO (UTC) para a API.
const paraISO = (v: string) => (v ? new Date(v).toISOString() : null);
const paraLocal = (v: string | null) => {
  if (!v) return "";
  const d = new Date(v);
  const off = d.getTimezoneOffset() * 60000;
  return new Date(d.getTime() - off).toISOString().slice(0, 16);
};

export default function Avisos() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [itens, setItens] = useState<AvisoTemporizado[]>([]);
  const toast = useToast();

  const recarregar = useCallback(async () => {
    setItens(await listarAvisos());
  }, []);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    recarregar().catch(() => toast({ tone: "danger", title: "Falha ao carregar avisos." }));
  }, [router, recarregar, toast]);

  if (!usuario) return null;

  return (
    <AppShell
      title="Avisos do dia"
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
        <NovoAviso onMudou={recarregar} />
        <Lista itens={itens} onMudou={recarregar} />
      </div>
    </AppShell>
  );
}

function NovoAviso({ onMudou }: { onMudou: () => Promise<void> }) {
  const toast = useToast();
  const [mensagem, setMensagem] = useState("");
  const [inicia, setInicia] = useState("");
  const [expira, setExpira] = useState("");

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    if (!mensagem.trim()) return;
    try {
      await criarAviso(mensagem.trim(), true, paraISO(inicia), paraISO(expira));
      setMensagem("");
      setInicia("");
      setExpira("");
      await onMudou();
      toast({ tone: "success", title: "Aviso publicado." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao publicar." });
    }
  }

  return (
    <Card>
      <CardHeader title="Novo aviso do dia" />
      <p className="mb-3 text-xs text-n-400">
        Enquanto vigente, o bot anexa este recado à resposta de quem inicia a conversa — sem
        mexer no celular. Deixe as datas em branco para valer imediatamente e sem prazo.
      </p>
      <form onSubmit={criar} className="flex flex-col gap-2">
        <Textarea
          value={mensagem}
          onChange={(e) => setMensagem(e.target.value)}
          rows={2}
          placeholder='Ex.: "Por motivo de saúde, a secretaria não abre à tarde hoje."'
        />
        <div className="flex flex-wrap gap-2">
          <label className="text-xs text-n-500">
            Início
            <Input type="datetime-local" value={inicia} onChange={(e) => setInicia(e.target.value)} />
          </label>
          <label className="text-xs text-n-500">
            Expira em
            <Input type="datetime-local" value={expira} onChange={(e) => setExpira(e.target.value)} />
          </label>
        </div>
        <div>
          <Button size="sm" type="submit" leftIcon={<PlusIcon size={15} />}>
            Publicar aviso
          </Button>
        </div>
      </form>
    </Card>
  );
}

function Lista({
  itens,
  onMudou,
}: {
  itens: AvisoTemporizado[];
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [editando, setEditando] = useState<AvisoTemporizado | null>(null);
  const [excluindo, setExcluindo] = useState<AvisoTemporizado | null>(null);

  async function alternarAtivo(a: AvisoTemporizado) {
    try {
      await atualizarAviso(a.id, a.mensagem, !a.ativo, a.inicia_em, a.expira_em);
      await onMudou();
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao alternar." });
    }
  }

  async function confirmarExclusao() {
    if (!excluindo) return;
    try {
      await removerAviso(excluindo.id);
      setExcluindo(null);
      await onMudou();
      toast({ tone: "success", title: "Aviso removido." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao remover." });
    }
  }

  return (
    <Card>
      <CardHeader title={`Avisos (${itens.length})`} />
      {itens.length === 0 ? (
        <p className="text-sm text-n-500">Nenhum aviso cadastrado ainda.</p>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Mensagem</Th>
                <Th>Vigência</Th>
                <Th>Status</Th>
                <Th className="text-right">Ações</Th>
              </tr>
            </thead>
            <tbody>
              {itens.map((a) => (
                <Tr key={a.id}>
                  <Td className="max-w-[360px] text-xs text-n-700">
                    <span className="line-clamp-2">{a.mensagem}</span>
                  </Td>
                  <Td className="text-xs text-n-500">
                    {a.inicia_em ? new Date(a.inicia_em).toLocaleString("pt-BR") : "imediato"}
                    {" → "}
                    {a.expira_em ? new Date(a.expira_em).toLocaleString("pt-BR") : "sem prazo"}
                  </Td>
                  <Td>
                    {a.vigente ? (
                      <Badge tone="success" dot>
                        Vigente
                      </Badge>
                    ) : a.ativo ? (
                      <Badge tone="warning">Fora da janela</Badge>
                    ) : (
                      <Badge tone="neutral">Inativo</Badge>
                    )}
                  </Td>
                  <Td className="text-right">
                    <div className="flex justify-end gap-1.5">
                      <Button size="sm" variant="secondary" onClick={() => alternarAtivo(a)}>
                        {a.ativo ? "Desativar" : "Ativar"}
                      </Button>
                      <Button size="sm" variant="secondary" onClick={() => setEditando(a)}>
                        Editar
                      </Button>
                      <Button size="sm" variant="danger" onClick={() => setExcluindo(a)}>
                        Excluir
                      </Button>
                    </div>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      )}

      {editando && (
        <EditarAviso aviso={editando} onClose={() => setEditando(null)} onMudou={onMudou} />
      )}

      <ConfirmDialog
        open={excluindo !== null}
        onClose={() => setExcluindo(null)}
        onConfirm={confirmarExclusao}
        title="Excluir aviso"
        message={excluindo ? "Remover este aviso do dia?" : ""}
      />
    </Card>
  );
}

function EditarAviso({
  aviso,
  onClose,
  onMudou,
}: {
  aviso: AvisoTemporizado;
  onClose: () => void;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [mensagem, setMensagem] = useState(aviso.mensagem);
  const [inicia, setInicia] = useState(paraLocal(aviso.inicia_em));
  const [expira, setExpira] = useState(paraLocal(aviso.expira_em));

  async function salvar() {
    if (!mensagem.trim()) return;
    try {
      await atualizarAviso(aviso.id, mensagem.trim(), aviso.ativo, paraISO(inicia), paraISO(expira));
      onClose();
      await onMudou();
      toast({ tone: "success", title: "Aviso atualizado." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao salvar." });
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Editar aviso"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancelar
          </Button>
          <Button size="sm" onClick={salvar}>
            Salvar
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Textarea value={mensagem} onChange={(e) => setMensagem(e.target.value)} rows={3} />
        <label className="text-xs text-n-500">
          Início
          <Input type="datetime-local" value={inicia} onChange={(e) => setInicia(e.target.value)} />
        </label>
        <label className="text-xs text-n-500">
          Expira em
          <Input type="datetime-local" value={expira} onChange={(e) => setExpira(e.target.value)} />
        </label>
      </div>
    </Modal>
  );
}
