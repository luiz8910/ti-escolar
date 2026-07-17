"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  atualizarStatusImpressao,
  criarImpressao,
  getSessao,
  Impressao,
  listarFilaImpressao,
  listarProfessores,
  logout,
  Professor,
  removerImpressao,
  StatusImpressao,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/form";
import { TableWrap, Table, Th, Td, Tr } from "@/components/ui/Table";
import { Badge } from "@/components/ui/Badge";
import { useToast } from "@/components/ui/Toast";
import { PlusIcon, PrintIcon } from "@/components/ui/icons";

const STATUS_LABEL: Record<StatusImpressao, string> = {
  pendente: "Pendente",
  em_processo: "Em processo",
  concluida: "Concluída",
  cancelada: "Cancelada",
};
const STATUS_TONE: Record<StatusImpressao, "neutral" | "brand" | "success" | "danger"> = {
  pendente: "brand",
  em_processo: "neutral",
  concluida: "success",
  cancelada: "danger",
};

export default function FilaImpressao() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [itens, setItens] = useState<Impressao[]>([]);
  const [professores, setProfessores] = useState<Professor[]>([]);
  const [filtro, setFiltro] = useState<StatusImpressao | "">("");
  const toast = useToast();

  const recarregar = useCallback(async () => {
    const [fila, profs] = await Promise.all([
      listarFilaImpressao(filtro || undefined),
      listarProfessores(),
    ]);
    setItens(fila);
    setProfessores(profs);
  }, [filtro]);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    recarregar().catch(() => toast({ tone: "danger", title: "Falha ao carregar a fila." }));
  }, [router, recarregar, toast]);

  async function mudarStatus(id: string, status: StatusImpressao) {
    try {
      await atualizarStatusImpressao(id, status);
      await recarregar();
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao atualizar." });
    }
  }

  async function remover(id: string) {
    try {
      await removerImpressao(id);
      await recarregar();
      toast({ tone: "success", title: "Solicitação removida." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao remover." });
    }
  }

  if (!usuario) return null;

  return (
    <AppShell
      title="Fila de impressão"
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
        <NovaSolicitacao professores={professores} onMudou={recarregar} />
        <Card>
          <CardHeader
            title={`Fila (${itens.length})`}
            action={
              <Select
                className="w-44"
                value={filtro}
                onChange={(e) => setFiltro(e.target.value as StatusImpressao | "")}
              >
                <option value="">Todos os status</option>
                <option value="pendente">Pendentes</option>
                <option value="em_processo">Em processo</option>
                <option value="concluida">Concluídas</option>
                <option value="cancelada">Canceladas</option>
              </Select>
            }
          />
          {itens.length === 0 ? (
            <p className="text-sm text-n-500">Nenhuma solicitação na fila.</p>
          ) : (
            <TableWrap>
              <Table>
                <thead>
                  <tr>
                    <Th>Arquivo</Th>
                    <Th>Professor</Th>
                    <Th>Parâmetros</Th>
                    <Th>Status</Th>
                    <Th className="text-right">Ações</Th>
                  </tr>
                </thead>
                <tbody>
                  {itens.map((s) => (
                    <Tr key={s.id}>
                      <Td className="font-medium">
                        <span className="inline-flex items-center gap-1.5">
                          <PrintIcon size={14} /> {s.arquivo_nome}
                        </span>
                        {s.observacao && (
                          <div className="mt-0.5 text-xs text-n-400">{s.observacao}</div>
                        )}
                      </Td>
                      <Td className="text-xs text-n-600">{s.professor_nome || "—"}</Td>
                      <Td className="text-xs text-n-600">
                        {s.copias} cópia(s) · {s.colorido ? "Colorido" : "P&B"} ·{" "}
                        {s.frente_verso ? "Frente e verso" : "Só frente"}
                      </Td>
                      <Td>
                        <Badge tone={STATUS_TONE[s.status]}>{STATUS_LABEL[s.status]}</Badge>
                      </Td>
                      <Td className="text-right">
                        <div className="flex flex-wrap justify-end gap-1.5">
                          {s.status === "pendente" && (
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => mudarStatus(s.id, "em_processo")}
                            >
                              Iniciar
                            </Button>
                          )}
                          {s.status !== "concluida" && s.status !== "cancelada" && (
                            <Button size="sm" onClick={() => mudarStatus(s.id, "concluida")}>
                              Concluir
                            </Button>
                          )}
                          {s.status !== "cancelada" && s.status !== "concluida" && (
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => mudarStatus(s.id, "cancelada")}
                            >
                              Cancelar
                            </Button>
                          )}
                          <Button size="sm" variant="danger" onClick={() => remover(s.id)}>
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
        </Card>
      </div>
    </AppShell>
  );
}

function NovaSolicitacao({
  professores,
  onMudou,
}: {
  professores: Professor[];
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [arquivo, setArquivo] = useState("");
  const [professorId, setProfessorId] = useState("");
  const [copias, setCopias] = useState(1);
  const [colorido, setColorido] = useState(false);
  const [frenteVerso, setFrenteVerso] = useState(false);
  const [observacao, setObservacao] = useState("");

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    if (!arquivo.trim() || copias < 1) return;
    try {
      await criarImpressao({
        arquivo_nome: arquivo.trim(),
        professor_id: professorId || null,
        copias,
        colorido,
        frente_verso: frenteVerso,
        observacao: observacao.trim(),
      });
      setArquivo("");
      setProfessorId("");
      setCopias(1);
      setColorido(false);
      setFrenteVerso(false);
      setObservacao("");
      await onMudou();
      toast({ tone: "success", title: "Solicitação adicionada à fila." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao criar." });
    }
  }

  return (
    <Card>
      <CardHeader title="Nova solicitação de impressão" />
      <form onSubmit={criar} className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          <Input
            className="flex-1 min-w-[200px]"
            value={arquivo}
            onChange={(e) => setArquivo(e.target.value)}
            placeholder="Nome do arquivo, ex.: prova_2bim_5A.pdf"
          />
          <Select className="w-52" value={professorId} onChange={(e) => setProfessorId(e.target.value)}>
            <option value="">— Professor (opcional) —</option>
            {professores.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </Select>
          <Input
            className="w-28"
            type="number"
            min={1}
            value={copias}
            onChange={(e) => setCopias(Number(e.target.value))}
            placeholder="Cópias"
          />
        </div>
        <div className="flex flex-wrap items-center gap-4 text-sm text-n-600">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={colorido} onChange={(e) => setColorido(e.target.checked)} />
            Colorido
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={frenteVerso}
              onChange={(e) => setFrenteVerso(e.target.checked)}
            />
            Frente e verso
          </label>
          <Input
            className="flex-1 min-w-[160px]"
            value={observacao}
            onChange={(e) => setObservacao(e.target.value)}
            placeholder="Observação (opcional)"
          />
        </div>
        <div>
          <Button size="sm" type="submit" leftIcon={<PlusIcon size={15} />}>
            Adicionar à fila
          </Button>
        </div>
      </form>
    </Card>
  );
}
