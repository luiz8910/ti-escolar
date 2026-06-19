"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Aluno,
  atualizarAluno,
  cadastrarAluno,
  desvincularResponsavelDoAluno,
  getSessao,
  listarAlunos,
  listarPais,
  listarSalas,
  logout,
  Pai,
  removerAluno,
  Sala,
  Usuario,
  vincularResponsavelAoAluno,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select, Field } from "@/components/ui/form";
import { TableWrap, Table, Th, Td, Tr } from "@/components/ui/Table";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { PlusIcon } from "@/components/ui/icons";

export default function Alunos() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [alunos, setAlunos] = useState<Aluno[]>([]);
  const [salas, setSalas] = useState<Sala[]>([]);
  const [pais, setPais] = useState<Pai[]>([]);
  const [filtroSala, setFiltroSala] = useState("");
  const toast = useToast();

  const recarregar = useCallback(async () => {
    const [as, ss, ps] = await Promise.all([listarAlunos(), listarSalas(), listarPais()]);
    setAlunos(as);
    setSalas(ss);
    setPais(ps);
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

  const visiveis = useMemo(
    () => (filtroSala ? alunos.filter((a) => a.sala_id === filtroSala) : alunos),
    [alunos, filtroSala],
  );

  if (!usuario) return null;

  return (
    <AppShell
      title="Alunos"
      user={{
        name: usuario.nome,
        role: usuario.papel === "super_admin" ? "Super Admin" : "Admin da escola",
      }}
      tenantName="Escola Demonstração"
      isSuperAdmin={usuario.papel === "super_admin"}
      onLogout={sair}
    >
      <div className="flex flex-col gap-[18px]">
        <AlunoForm salas={salas} onMudou={recarregar} />
        <ListaAlunos
          alunos={visiveis}
          salas={salas}
          pais={pais}
          filtroSala={filtroSala}
          onFiltrar={setFiltroSala}
          onMudou={recarregar}
        />
      </div>
    </AppShell>
  );
}

// --------------------------------------------------------------------------- //
function AlunoForm({ salas, onMudou }: { salas: Sala[]; onMudou: () => Promise<void> }) {
  const toast = useToast();
  const [nome, setNome] = useState("");
  const [matricula, setMatricula] = useState("");
  const [salaId, setSalaId] = useState("");

  async function cadastrar(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim() || !salaId) return;
    try {
      await cadastrarAluno(nome.trim(), salaId, matricula.trim());
      setNome("");
      setMatricula("");
      setSalaId("");
      await onMudou();
      toast({ tone: "success", title: "Aluno cadastrado." });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao cadastrar aluno.",
      });
    }
  }

  if (salas.length === 0) {
    return (
      <Card>
        <CardHeader title="Cadastrar aluno" />
        <p className="text-sm text-n-500">
          Cadastre uma série em <strong>Salas e pais</strong> antes de matricular alunos — todo
          aluno pertence a uma série.
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader title="Cadastrar aluno" />
      <form onSubmit={cadastrar} className="flex flex-wrap gap-2">
        <Input
          className="flex-1 min-w-[180px]"
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          placeholder="Nome do aluno"
        />
        <Input
          className="w-40"
          value={matricula}
          onChange={(e) => setMatricula(e.target.value)}
          placeholder="Matrícula (opcional)"
        />
        <Select
          className="w-48"
          value={salaId}
          onChange={(e) => setSalaId(e.target.value)}
          required
        >
          <option value="" disabled>
            Selecione a série…
          </option>
          {salas.map((s) => (
            <option key={s.id} value={s.id}>
              {s.nome}
            </option>
          ))}
        </Select>
        <Button size="sm" type="submit" disabled={!salaId} leftIcon={<PlusIcon size={15} />}>
          Cadastrar
        </Button>
      </form>
      <p className="mt-2 text-xs text-n-400">
        Vincule responsáveis depois, em “Responsáveis”. Cada aluno pertence a uma série.
      </p>
    </Card>
  );
}

// --------------------------------------------------------------------------- //
function ListaAlunos({
  alunos,
  salas,
  pais,
  filtroSala,
  onFiltrar,
  onMudou,
}: {
  alunos: Aluno[];
  salas: Sala[];
  pais: Pai[];
  filtroSala: string;
  onFiltrar: (v: string) => void;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [editando, setEditando] = useState<Aluno | null>(null);
  const [gerenciando, setGerenciando] = useState<Aluno | null>(null);
  const [excluindo, setExcluindo] = useState<Aluno | null>(null);

  async function confirmarExclusao() {
    if (!excluindo) return;
    try {
      await removerAluno(excluindo.id);
      setExcluindo(null);
      await onMudou();
      toast({ tone: "success", title: "Aluno excluído." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao excluir." });
    }
  }

  return (
    <Card>
      <CardHeader
        title="Alunos cadastrados"
        count={alunos.length}
        action={
          <Select className="w-48" value={filtroSala} onChange={(e) => onFiltrar(e.target.value)}>
            <option value="">Todas as séries</option>
            {salas.map((s) => (
              <option key={s.id} value={s.id}>
                {s.nome}
              </option>
            ))}
          </Select>
        }
      />

      <TableWrap>
        <Table>
          <thead>
            <tr>
              <Th>Aluno</Th>
              <Th>Matrícula</Th>
              <Th>Série</Th>
              <Th>Responsáveis</Th>
              <Th>Situação</Th>
              <Th className="text-right">Ações</Th>
            </tr>
          </thead>
          <tbody>
            {alunos.map((a) => (
              <Tr key={a.id}>
                <Td className="font-medium">{a.nome}</Td>
                <Td className="font-mono text-xs text-n-500">{a.matricula || "—"}</Td>
                <Td className="text-n-600">{a.sala_nome || "Sem série"}</Td>
                <Td>
                  <button
                    onClick={() => setGerenciando(a)}
                    className="text-xs font-semibold text-brand-700 hover:underline"
                  >
                    {a.responsaveis.length} responsável(is)
                  </button>
                </Td>
                <Td>
                  <span
                    className={
                      "rounded-full px-2 py-0.5 text-[11px] font-bold " +
                      (a.ativo ? "bg-[#e8f7f1] text-[#0d8a78]" : "bg-n-100 text-n-500")
                    }
                  >
                    {a.ativo ? "Ativo" : "Ex-aluno"}
                  </span>
                </Td>
                <Td className="text-right">
                  <span className="flex items-center justify-end gap-3">
                    <button
                      onClick={() => setGerenciando(a)}
                      className="text-xs font-semibold text-n-500 hover:text-n-800"
                    >
                      Responsáveis
                    </button>
                    <button
                      onClick={() => setEditando(a)}
                      className="text-xs font-semibold text-n-500 hover:text-n-800"
                    >
                      Editar
                    </button>
                    <button
                      onClick={() => setExcluindo(a)}
                      className="text-xs font-semibold text-danger hover:underline"
                    >
                      Excluir
                    </button>
                  </span>
                </Td>
              </Tr>
            ))}
            {alunos.length === 0 && (
              <Tr>
                <Td colSpan={6} className="text-n-400">
                  Nenhum aluno cadastrado ainda.
                </Td>
              </Tr>
            )}
          </tbody>
        </Table>
      </TableWrap>

      {editando && (
        <EditarAlunoModal
          aluno={editando}
          salas={salas}
          onClose={() => setEditando(null)}
          onMudou={onMudou}
        />
      )}

      {gerenciando && (
        <ResponsaveisModal
          aluno={gerenciando}
          pais={pais}
          onClose={() => setGerenciando(null)}
          onMudou={onMudou}
        />
      )}

      <ConfirmDialog
        open={!!excluindo}
        onClose={() => setExcluindo(null)}
        onConfirm={confirmarExclusao}
        title="Excluir aluno"
        message={`Excluir o aluno "${excluindo?.nome}"? Os responsáveis continuam cadastrados.`}
      />
    </Card>
  );
}

// --------------------------------------------------------------------------- //
function EditarAlunoModal({
  aluno,
  salas,
  onClose,
  onMudou,
}: {
  aluno: Aluno;
  salas: Sala[];
  onClose: () => void;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [nome, setNome] = useState(aluno.nome);
  const [matricula, setMatricula] = useState(aluno.matricula);
  const [salaId, setSalaId] = useState(aluno.sala_id);
  const [ativo, setAtivo] = useState(aluno.ativo);

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim() || !salaId) return;
    try {
      await atualizarAluno(aluno.id, nome.trim(), salaId, matricula.trim(), ativo);
      onClose();
      await onMudou();
      toast({ tone: "success", title: "Aluno atualizado." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao salvar." });
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Editar aluno"
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
      <form onSubmit={salvar} className="flex flex-col gap-3">
        <Field label="Nome do aluno">
          <Input autoFocus value={nome} onChange={(e) => setNome(e.target.value)} />
        </Field>
        <Field label="Matrícula">
          <Input value={matricula} onChange={(e) => setMatricula(e.target.value)} />
        </Field>
        <Field label="Série / turma">
          <Select value={salaId} onChange={(e) => setSalaId(e.target.value)} required>
            {salas.map((s) => (
              <option key={s.id} value={s.id}>
                {s.nome}
              </option>
            ))}
          </Select>
        </Field>
        <label className="flex items-center gap-2 text-[13px] font-semibold text-n-700">
          <input type="checkbox" checked={ativo} onChange={(e) => setAtivo(e.target.checked)} />
          Aluno ativo (desmarque para marcar como ex-aluno)
        </label>
      </form>
    </Modal>
  );
}

// --------------------------------------------------------------------------- //
function ResponsaveisModal({
  aluno,
  pais,
  onClose,
  onMudou,
}: {
  aluno: Aluno;
  pais: Pai[];
  onClose: () => void;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  // Mantém uma cópia local dos vínculos para refletir as mudanças sem fechar o modal.
  const [vinculados, setVinculados] = useState<Pai[]>(aluno.responsaveis);
  const [paiId, setPaiId] = useState("");

  const naoVinculados = pais.filter((p) => !vinculados.some((v) => v.id === p.id));

  async function vincular(e: React.FormEvent) {
    e.preventDefault();
    if (!paiId) return;
    const pai = pais.find((p) => p.id === paiId);
    try {
      await vincularResponsavelAoAluno(aluno.id, paiId);
      if (pai) setVinculados((atual) => [...atual, pai]);
      setPaiId("");
      await onMudou();
      toast({ tone: "success", title: "Responsável vinculado." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao vincular." });
    }
  }

  async function desvincular(p: Pai) {
    try {
      await desvincularResponsavelDoAluno(aluno.id, p.id);
      setVinculados((atual) => atual.filter((v) => v.id !== p.id));
      await onMudou();
      toast({ tone: "success", title: "Responsável removido." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao desvincular." });
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`Responsáveis — ${aluno.nome}`}
      footer={
        <Button size="sm" onClick={onClose}>
          Concluir
        </Button>
      }
    >
      <div className="flex flex-col gap-3">
        <ul className="flex flex-col gap-1.5">
          {vinculados.map((p) => (
            <li
              key={p.id}
              className="flex items-center gap-2 rounded-[10px] bg-n-50 px-3 py-2 text-[13px]"
            >
              <span className="flex-1 font-medium text-n-800">{p.nome}</span>
              <span className="font-mono text-xs text-n-500">{p.telefone}</span>
              <button
                onClick={() => desvincular(p)}
                className="text-xs font-semibold text-danger hover:underline"
              >
                Remover
              </button>
            </li>
          ))}
          {vinculados.length === 0 && (
            <li className="px-1 py-2 text-sm text-n-400">Nenhum responsável vinculado.</li>
          )}
        </ul>

        <form onSubmit={vincular} className="flex gap-2 border-t border-n-100 pt-3">
          <Select className="flex-1" value={paiId} onChange={(e) => setPaiId(e.target.value)}>
            <option value="">Vincular responsável cadastrado…</option>
            {naoVinculados.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome} — {p.telefone}
              </option>
            ))}
          </Select>
          <Button
            variant="secondary"
            size="sm"
            type="submit"
            disabled={!paiId}
            leftIcon={<PlusIcon size={14} />}
          >
            Vincular
          </Button>
        </form>
      </div>
    </Modal>
  );
}
