"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  atualizarRespostaRapida,
  criarRespostaRapida,
  getSessao,
  listarRespostasRapidas,
  logout,
  removerRespostaRapida,
  RespostaRapida,
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

export default function RespostasRapidas() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [itens, setItens] = useState<RespostaRapida[]>([]);
  const toast = useToast();

  const recarregar = useCallback(async () => {
    setItens(await listarRespostasRapidas());
  }, []);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    recarregar().catch(() => toast({ tone: "danger", title: "Falha ao carregar respostas." }));
  }, [router, recarregar, toast]);

  if (!usuario) return null;

  return (
    <AppShell
      title="Respostas rápidas"
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
        <NovaResposta onMudou={recarregar} />
        <Lista itens={itens} onMudou={recarregar} />
      </div>
    </AppShell>
  );
}

function NovaResposta({ onMudou }: { onMudou: () => Promise<void> }) {
  const toast = useToast();
  const [chave, setChave] = useState("");
  const [conteudo, setConteudo] = useState("");

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    if (!chave.trim() || !conteudo.trim()) return;
    try {
      await criarRespostaRapida(chave.trim(), conteudo.trim());
      setChave("");
      setConteudo("");
      await onMudou();
      toast({ tone: "success", title: "Resposta rápida criada e indexada no RAG." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao criar." });
    }
  }

  return (
    <Card>
      <CardHeader title="Nova resposta rápida" />
      <p className="mb-3 text-xs text-n-400">
        Um atalho da secretaria (chave + conteúdo). O bot responde automaticamente com base nele.
      </p>
      <form onSubmit={criar} className="flex flex-col gap-2">
        <Input
          value={chave}
          onChange={(e) => setChave(e.target.value)}
          placeholder='Chave, ex.: "Horário do portão"'
        />
        <Textarea
          value={conteudo}
          onChange={(e) => setConteudo(e.target.value)}
          placeholder="Conteúdo da resposta que o bot usará"
          rows={3}
        />
        <div>
          <Button size="sm" type="submit" leftIcon={<PlusIcon size={15} />}>
            Criar
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
  itens: RespostaRapida[];
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [editando, setEditando] = useState<RespostaRapida | null>(null);
  const [excluindo, setExcluindo] = useState<RespostaRapida | null>(null);

  async function alternarAtivo(r: RespostaRapida) {
    try {
      await atualizarRespostaRapida(r.id, r.chave, r.conteudo, !r.ativo);
      await onMudou();
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao alternar." });
    }
  }

  async function confirmarExclusao() {
    if (!excluindo) return;
    try {
      await removerRespostaRapida(excluindo.id);
      setExcluindo(null);
      await onMudou();
      toast({ tone: "success", title: "Resposta rápida removida." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao remover." });
    }
  }

  return (
    <Card>
      <CardHeader title={`Respostas rápidas (${itens.length})`} />
      {itens.length === 0 ? (
        <p className="text-sm text-n-500">Nenhuma resposta rápida cadastrada ainda.</p>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Chave</Th>
                <Th>Conteúdo</Th>
                <Th>Status</Th>
                <Th className="text-right">Ações</Th>
              </tr>
            </thead>
            <tbody>
              {itens.map((r) => (
                <Tr key={r.id}>
                  <Td className="font-medium">{r.chave}</Td>
                  <Td className="max-w-[420px] text-xs text-n-600">
                    <span className="line-clamp-2">{r.conteudo}</span>
                  </Td>
                  <Td>
                    {r.ativo ? (
                      <Badge tone="success" dot>
                        Ativa (no RAG)
                      </Badge>
                    ) : (
                      <Badge tone="neutral">Inativa</Badge>
                    )}
                  </Td>
                  <Td className="text-right">
                    <div className="flex justify-end gap-1.5">
                      <Button size="sm" variant="secondary" onClick={() => alternarAtivo(r)}>
                        {r.ativo ? "Desativar" : "Ativar"}
                      </Button>
                      <Button size="sm" variant="secondary" onClick={() => setEditando(r)}>
                        Editar
                      </Button>
                      <Button size="sm" variant="danger" onClick={() => setExcluindo(r)}>
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
        <EditarResposta
          resposta={editando}
          onClose={() => setEditando(null)}
          onMudou={onMudou}
        />
      )}

      <ConfirmDialog
        open={excluindo !== null}
        onClose={() => setExcluindo(null)}
        onConfirm={confirmarExclusao}
        title="Excluir resposta rápida"
        message={excluindo ? `Excluir “${excluindo.chave}”? Ela sairá da base do bot.` : ""}
      />
    </Card>
  );
}

function EditarResposta({
  resposta,
  onClose,
  onMudou,
}: {
  resposta: RespostaRapida;
  onClose: () => void;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [chave, setChave] = useState(resposta.chave);
  const [conteudo, setConteudo] = useState(resposta.conteudo);

  async function salvar() {
    if (!chave.trim() || !conteudo.trim()) return;
    try {
      await atualizarRespostaRapida(resposta.id, chave.trim(), conteudo.trim(), resposta.ativo);
      onClose();
      await onMudou();
      toast({ tone: "success", title: "Resposta rápida atualizada." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao salvar." });
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Editar resposta rápida"
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
        <Input value={chave} onChange={(e) => setChave(e.target.value)} placeholder="Chave" />
        <Textarea
          value={conteudo}
          onChange={(e) => setConteudo(e.target.value)}
          rows={4}
          placeholder="Conteúdo"
        />
      </div>
    </Modal>
  );
}
