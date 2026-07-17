"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  getSessao,
  listarRecados,
  logout,
  publicarRecado,
  RecadoResumo,
  RecadoStatusLeitura,
  removerRecado,
  renotificarRecado,
  statusLeituraRecado,
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
import { PlusIcon, CheckIcon, BellIcon } from "@/components/ui/icons";

export default function Mural() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [itens, setItens] = useState<RecadoResumo[]>([]);
  const toast = useToast();

  const recarregar = useCallback(async () => {
    setItens(await listarRecados());
  }, []);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    recarregar().catch(() => toast({ tone: "danger", title: "Falha ao carregar recados." }));
  }, [router, recarregar, toast]);

  if (!usuario) return null;

  return (
    <AppShell
      title="Mural do professor"
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
        <NovoRecado onMudou={recarregar} />
        <Lista itens={itens} onMudou={recarregar} />
      </div>
    </AppShell>
  );
}

function NovoRecado({ onMudou }: { onMudou: () => Promise<void> }) {
  const toast = useToast();
  const [titulo, setTitulo] = useState("");
  const [corpo, setCorpo] = useState("");

  async function publicar(e: React.FormEvent) {
    e.preventDefault();
    if (!titulo.trim() || !corpo.trim()) return;
    try {
      await publicarRecado(titulo.trim(), corpo.trim());
      setTitulo("");
      setCorpo("");
      await onMudou();
      toast({ tone: "success", title: "Recado publicado no mural." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao publicar." });
    }
  }

  return (
    <Card>
      <CardHeader title="Publicar recado" />
      <p className="mb-3 text-xs text-n-400">
        Vai para o mural de todos os professores. Você acompanha quem confirmou a leitura e pode
        re-notificar quem ainda não viu.
      </p>
      <form onSubmit={publicar} className="flex flex-col gap-2">
        <Input value={titulo} onChange={(e) => setTitulo(e.target.value)} placeholder="Título" />
        <Textarea
          value={corpo}
          onChange={(e) => setCorpo(e.target.value)}
          rows={3}
          placeholder="Mensagem do recado"
        />
        <div>
          <Button size="sm" type="submit" leftIcon={<PlusIcon size={15} />}>
            Publicar
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
  itens: RecadoResumo[];
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [detalhe, setDetalhe] = useState<RecadoStatusLeitura | null>(null);
  const [excluindo, setExcluindo] = useState<RecadoResumo | null>(null);

  async function verLeitura(id: string) {
    try {
      setDetalhe(await statusLeituraRecado(id));
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao abrir." });
    }
  }

  async function renotificar(id: string) {
    try {
      const r = await renotificarRecado(id);
      toast({
        tone: "success",
        title:
          r.avisados > 0
            ? `${r.avisados} professor(es) re-notificado(s) por WhatsApp.`
            : "Todos já leram — ninguém a notificar.",
      });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao notificar." });
    }
  }

  async function confirmarExclusao() {
    if (!excluindo) return;
    try {
      await removerRecado(excluindo.id);
      setExcluindo(null);
      await onMudou();
      toast({ tone: "success", title: "Recado removido." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao remover." });
    }
  }

  return (
    <Card>
      <CardHeader title={`Recados (${itens.length})`} />
      {itens.length === 0 ? (
        <p className="text-sm text-n-500">Nenhum recado publicado ainda.</p>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Recado</Th>
                <Th>Leitura</Th>
                <Th className="text-right">Ações</Th>
              </tr>
            </thead>
            <tbody>
              {itens.map((r) => (
                <Tr key={r.id}>
                  <Td>
                    <div className="font-medium">{r.titulo}</div>
                    <div className="mt-0.5 text-xs text-n-400">
                      {new Date(r.criado_em).toLocaleString("pt-BR")}
                    </div>
                  </Td>
                  <Td>
                    {r.total_nao_lidos === 0 && r.total_professores > 0 ? (
                      <Badge tone="success" dot>
                        Todos leram ({r.total_lidos}/{r.total_professores})
                      </Badge>
                    ) : (
                      <Badge tone="warning">
                        {r.total_lidos}/{r.total_professores} leram · {r.total_nao_lidos} pendente(s)
                      </Badge>
                    )}
                  </Td>
                  <Td className="text-right">
                    <div className="flex flex-wrap justify-end gap-1.5">
                      <Button size="sm" variant="secondary" onClick={() => verLeitura(r.id)}>
                        Ver leitura
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        leftIcon={<BellIcon size={14} />}
                        onClick={() => renotificar(r.id)}
                        disabled={r.total_nao_lidos === 0}
                      >
                        Re-notificar
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

      {detalhe && <DetalheLeitura detalhe={detalhe} onClose={() => setDetalhe(null)} />}

      <ConfirmDialog
        open={excluindo !== null}
        onClose={() => setExcluindo(null)}
        onConfirm={confirmarExclusao}
        title="Excluir recado"
        message={excluindo ? `Excluir “${excluindo.titulo}”?` : ""}
      />
    </Card>
  );
}

function DetalheLeitura({
  detalhe,
  onClose,
}: {
  detalhe: RecadoStatusLeitura;
  onClose: () => void;
}) {
  return (
    <Modal open onClose={onClose} title={detalhe.titulo}>
      <div className="flex flex-col gap-4">
        <p className="whitespace-pre-wrap text-sm text-n-700">{detalhe.corpo}</p>
        <div>
          <div className="mb-1.5 text-xs font-bold text-success">
            ✓ Leram ({detalhe.lidos.length})
          </div>
          {detalhe.lidos.length === 0 ? (
            <p className="text-xs text-n-400">Ninguém confirmou ainda.</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {detalhe.lidos.map((p) => (
                <li key={p.professor_id} className="flex items-center gap-2 text-sm text-n-700">
                  <CheckIcon size={14} /> {p.nome}
                  {p.lido_em && (
                    <span className="text-xs text-n-400">
                      · {new Date(p.lido_em).toLocaleString("pt-BR")}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <div className="mb-1.5 text-xs font-bold text-[#92600a]">
            Não leram ({detalhe.nao_lidos.length})
          </div>
          {detalhe.nao_lidos.length === 0 ? (
            <p className="text-xs text-n-400">Todos leram. 🎉</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {detalhe.nao_lidos.map((p) => (
                <li key={p.professor_id} className="text-sm text-n-700">
                  {p.nome} <span className="font-mono text-xs text-n-400">{p.telefone}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Modal>
  );
}
