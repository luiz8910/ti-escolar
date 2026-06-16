"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  atualizarPai,
  atualizarSala,
  cadastrarPai,
  criarSala,
  desvincularPaiDaSala,
  getSessao,
  listarPais,
  listarSalas,
  logout,
  Pai,
  relatorioPaisDaSala,
  removerPai,
  removerSala,
  Sala,
  Usuario,
  vincularPaiASala,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select, Field } from "@/components/ui/form";
import { TableWrap, Table, Th, Td, Tr } from "@/components/ui/Table";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { UsersIcon, PlusIcon, PrintIcon } from "@/components/ui/icons";

export default function SalasEPais() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [salas, setSalas] = useState<Sala[]>([]);
  const [pais, setPais] = useState<Pai[]>([]);
  const [selecionada, setSelecionada] = useState<Sala | null>(null);
  const toast = useToast();

  const recarregar = useCallback(async () => {
    const [ss, ps] = await Promise.all([listarSalas(), listarPais()]);
    setSalas(ss);
    setPais(ps);
    setSelecionada((atual) => (atual ? ss.find((s) => s.id === atual.id) ?? null : null));
  }, []);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    recarregar().catch(() => toast({ tone: "danger", title: "Falha ao carregar dados." }));
  }, [router, recarregar, toast]);

  function sair() {
    logout();
    router.replace("/admin/login");
  }

  if (!usuario) return null;

  return (
    <AppShell
      title="Salas e pais"
      user={{
        name: usuario.nome,
        role: usuario.papel === "super_admin" ? "Super Admin" : "Admin da escola",
      }}
      tenantName="Escola Demonstração"
      isSuperAdmin={usuario.papel === "super_admin"}
      onLogout={sair}
    >
      <div className="flex flex-col gap-[18px]">
        <div className="grid grid-cols-1 gap-[18px] lg:grid-cols-[320px_1fr]">
          <SalasPanel
            salas={salas}
            selecionada={selecionada}
            onSelecionar={setSelecionada}
            onMudou={recarregar}
          />
          <SalaDetalhe sala={selecionada} pais={pais} onMudou={recarregar} />
        </div>

        <PaisPanel pais={pais} onMudou={recarregar} />
      </div>
    </AppShell>
  );
}

// --------------------------------------------------------------------------- //
function SalasPanel({
  salas,
  selecionada,
  onSelecionar,
  onMudou,
}: {
  salas: Sala[];
  selecionada: Sala | null;
  onSelecionar: (s: Sala) => void;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [nova, setNova] = useState("");
  const [editando, setEditando] = useState<Sala | null>(null);
  const [nomeEdicao, setNomeEdicao] = useState("");
  const [excluindo, setExcluindo] = useState<Sala | null>(null);

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    if (!nova.trim()) return;
    try {
      await criarSala(nova.trim());
      setNova("");
      await onMudou();
      toast({ tone: "success", title: "Sala criada." });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Não foi possível criar a sala.",
      });
    }
  }

  function abrirEdicao(sala: Sala) {
    setEditando(sala);
    setNomeEdicao(sala.nome);
  }

  async function salvarEdicao(e: React.FormEvent) {
    e.preventDefault();
    if (!editando || !nomeEdicao.trim() || nomeEdicao.trim() === editando.nome) {
      setEditando(null);
      return;
    }
    try {
      await atualizarSala(editando.id, nomeEdicao.trim(), editando.descricao);
      setEditando(null);
      await onMudou();
      toast({ tone: "success", title: "Sala renomeada." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao renomear." });
    }
  }

  async function confirmarExclusao() {
    if (!excluindo) return;
    try {
      await removerSala(excluindo.id);
      setExcluindo(null);
      await onMudou();
      toast({ tone: "success", title: "Sala excluída." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao excluir." });
    }
  }

  return (
    <Card className="flex flex-col">
      <CardHeader title="Salas (turmas)" count={salas.length} />
      <div className="flex flex-col gap-1">
        {salas.map((s) => {
          const active = selecionada?.id === s.id;
          return (
            <div
              key={s.id}
              className={
                "group flex items-center gap-2 rounded-[10px] px-3 py-2.5 text-[13px] font-semibold " +
                (active ? "bg-brand-600 text-white" : "text-n-700 hover:bg-n-50")
              }
            >
              <button onClick={() => onSelecionar(s)} className="flex flex-1 items-center gap-2 text-left">
                <span>{s.nome}</span>
                <span
                  className={
                    "rounded-full px-2 py-0.5 text-[11px] font-bold " +
                    (active ? "bg-white/20" : "bg-n-100 text-n-500")
                  }
                >
                  {s.total_pais}
                </span>
              </button>
              <button
                onClick={() => abrirEdicao(s)}
                title="Renomear"
                className={active ? "text-white/80 hover:text-white" : "text-n-400 hover:text-n-700"}
              >
                ✏️
              </button>
              <button
                onClick={() => setExcluindo(s)}
                title="Excluir"
                className={active ? "text-white/80 hover:text-white" : "text-n-400 hover:text-danger"}
              >
                🗑️
              </button>
            </div>
          );
        })}
        {salas.length === 0 && (
          <p className="px-3 py-2 text-sm text-n-400">Nenhuma sala cadastrada.</p>
        )}
      </div>

      <form onSubmit={criar} className="mt-auto flex gap-2 border-t border-n-100 pt-3.5">
        <Input
          value={nova}
          onChange={(e) => setNova(e.target.value)}
          placeholder="Nova sala (ex.: 4ª série B)"
        />
        <Button size="sm" type="submit" leftIcon={<PlusIcon size={15} />}>
          Criar
        </Button>
      </form>

      <Modal
        open={!!editando}
        onClose={() => setEditando(null)}
        title="Renomear sala"
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setEditando(null)}>
              Cancelar
            </Button>
            <Button size="sm" onClick={salvarEdicao}>
              Salvar
            </Button>
          </>
        }
      >
        <form onSubmit={salvarEdicao}>
          <Field label="Nome da sala">
            <Input
              autoFocus
              value={nomeEdicao}
              onChange={(e) => setNomeEdicao(e.target.value)}
            />
          </Field>
        </form>
      </Modal>

      <ConfirmDialog
        open={!!excluindo}
        onClose={() => setExcluindo(null)}
        onConfirm={confirmarExclusao}
        title="Excluir sala"
        message={`Excluir a sala "${excluindo?.nome}"? Os pais continuam cadastrados.`}
      />
    </Card>
  );
}

// --------------------------------------------------------------------------- //
function SalaDetalhe({
  sala,
  pais,
  onMudou,
}: {
  sala: Sala | null;
  pais: Pai[];
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [relatorio, setRelatorio] = useState<Pai[]>([]);
  const [paiId, setPaiId] = useState("");

  const carregarRelatorio = useCallback(async () => {
    if (!sala) {
      setRelatorio([]);
      return;
    }
    try {
      setRelatorio(await relatorioPaisDaSala(sala.id));
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao carregar relatório.",
      });
    }
  }, [sala, toast]);

  useEffect(() => {
    carregarRelatorio();
  }, [carregarRelatorio]);

  if (!sala) {
    return (
      <Card className="flex items-center justify-center">
        <EmptyState
          icon={<UsersIcon size={24} />}
          title="Selecione uma sala"
          description="Escolha uma sala para ver o relatório de pais e gerenciar vínculos."
        />
      </Card>
    );
  }

  const naoVinculados = pais.filter((p) => !relatorio.some((r) => r.id === p.id));

  async function vincular(e: React.FormEvent) {
    e.preventDefault();
    if (!paiId) return;
    try {
      await vincularPaiASala(sala!.id, paiId);
      setPaiId("");
      await Promise.all([carregarRelatorio(), onMudou()]);
      toast({ tone: "success", title: "Responsável vinculado." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao vincular." });
    }
  }

  async function desvincular(p: Pai) {
    try {
      await desvincularPaiDaSala(sala!.id, p.id);
      await Promise.all([carregarRelatorio(), onMudou()]);
      toast({ tone: "success", title: "Responsável removido da sala." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao desvincular." });
    }
  }

  return (
    <Card>
      <CardHeader
        title={
          <>
            Relatório — {sala.nome}{" "}
            <span className="font-semibold text-n-400">· {relatorio.length} responsável(is)</span>
          </>
        }
        action={
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<PrintIcon size={15} />}
            onClick={() => window.print()}
          >
            Imprimir / PDF
          </Button>
        }
      />

      <TableWrap>
        <Table>
          <thead>
            <tr>
              <Th>Responsável</Th>
              <Th>WhatsApp</Th>
              <Th className="text-right">Ações</Th>
            </tr>
          </thead>
          <tbody>
            {relatorio.map((p) => (
              <Tr key={p.id}>
                <Td className="font-medium">{p.nome}</Td>
                <Td className="font-mono text-xs text-n-500">{p.telefone}</Td>
                <Td className="text-right">
                  <button
                    onClick={() => desvincular(p)}
                    className="text-xs font-semibold text-danger hover:underline print:hidden"
                  >
                    Remover da sala
                  </button>
                </Td>
              </Tr>
            ))}
            {relatorio.length === 0 && (
              <Tr>
                <Td colSpan={3} className="text-n-400">
                  Nenhum responsável vinculado a esta sala.
                </Td>
              </Tr>
            )}
          </tbody>
        </Table>
      </TableWrap>

      <form onSubmit={vincular} className="mt-3.5 flex gap-2 print:hidden">
        <Select className="flex-1" value={paiId} onChange={(e) => setPaiId(e.target.value)}>
          <option value="">Vincular responsável já cadastrado…</option>
          {naoVinculados.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nome} — {p.telefone}
            </option>
          ))}
        </Select>
        <Button variant="secondary" size="sm" type="submit" disabled={!paiId} leftIcon={<PlusIcon size={14} />}>
          Vincular
        </Button>
      </form>
    </Card>
  );
}

// --------------------------------------------------------------------------- //
function PaisPanel({
  pais,
  onMudou,
}: {
  pais: Pai[];
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [nome, setNome] = useState("");
  const [telefone, setTelefone] = useState("");
  const [editando, setEditando] = useState<string | null>(null);
  const [excluindo, setExcluindo] = useState<Pai | null>(null);

  async function adicionar(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim() || !telefone.trim()) return;
    try {
      if (editando) {
        await atualizarPai(editando, nome.trim(), telefone.trim());
      } else {
        await cadastrarPai(nome.trim(), telefone.trim());
      }
      setNome("");
      setTelefone("");
      setEditando(null);
      await onMudou();
      toast({ tone: "success", title: editando ? "Responsável atualizado." : "Responsável cadastrado." });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao salvar responsável.",
      });
    }
  }

  function editar(p: Pai) {
    setEditando(p.id);
    setNome(p.nome);
    setTelefone(p.telefone);
  }

  function cancelar() {
    setEditando(null);
    setNome("");
    setTelefone("");
  }

  async function confirmarExclusao() {
    if (!excluindo) return;
    try {
      await removerPai(excluindo.id);
      setExcluindo(null);
      await onMudou();
      toast({ tone: "success", title: "Responsável excluído." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao excluir." });
    }
  }

  return (
    <Card>
      <CardHeader title="Pais / responsáveis cadastrados" count={pais.length} />

      <form onSubmit={adicionar} className="mb-4 flex flex-wrap gap-2">
        <Input
          className="flex-1"
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          placeholder="Nome do responsável"
        />
        <Input
          className="w-44"
          mono
          value={telefone}
          onChange={(e) => setTelefone(e.target.value)}
          placeholder="+5511999990000"
        />
        <Button size="sm" type="submit">
          {editando ? "Salvar" : "Cadastrar"}
        </Button>
        {editando && (
          <Button variant="secondary" size="sm" type="button" onClick={cancelar}>
            Cancelar
          </Button>
        )}
      </form>

      <TableWrap>
        <Table>
          <thead>
            <tr>
              <Th>Responsável</Th>
              <Th>WhatsApp</Th>
              <Th className="text-right">Ações</Th>
            </tr>
          </thead>
          <tbody>
            {pais.map((p) => (
              <Tr key={p.id}>
                <Td className="font-medium">{p.nome}</Td>
                <Td className="font-mono text-xs text-n-500">{p.telefone}</Td>
                <Td className="text-right">
                  <span className="flex items-center justify-end gap-3">
                    <button
                      onClick={() => editar(p)}
                      className="text-xs font-semibold text-n-500 hover:text-n-800"
                    >
                      Editar
                    </button>
                    <button
                      onClick={() => setExcluindo(p)}
                      className="text-xs font-semibold text-danger hover:underline"
                    >
                      Excluir
                    </button>
                  </span>
                </Td>
              </Tr>
            ))}
            {pais.length === 0 && (
              <Tr>
                <Td colSpan={3} className="text-n-400">
                  Nenhum responsável cadastrado ainda.
                </Td>
              </Tr>
            )}
          </tbody>
        </Table>
      </TableWrap>

      <ConfirmDialog
        open={!!excluindo}
        onClose={() => setExcluindo(null)}
        onConfirm={confirmarExclusao}
        title="Excluir responsável"
        message={`Excluir o responsável "${excluindo?.nome}"?`}
      />
    </Card>
  );
}
