"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  atualizarProfessor,
  cadastrarProfessor,
  definirProfessorDaSala,
  getSessao,
  listarProfessores,
  listarSalas,
  logout,
  Professor,
  removerProfessor,
  Sala,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/form";
import { TableWrap, Table, Th, Td, Tr } from "@/components/ui/Table";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { PlusIcon } from "@/components/ui/icons";

export default function Professores() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [professores, setProfessores] = useState<Professor[]>([]);
  const [salas, setSalas] = useState<Sala[]>([]);
  const toast = useToast();

  const recarregar = useCallback(async () => {
    const [ps, ss] = await Promise.all([listarProfessores(), listarSalas()]);
    setProfessores(ps);
    setSalas(ss);
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
      title="Professores"
      user={{
        name: usuario.nome,
        role: usuario.papel === "super_admin" ? "Super Admin" : "Admin da escola",
      }}
      tenantName="Escola Demonstração"
      isSuperAdmin={usuario.papel === "super_admin"}
      onLogout={sair}
    >
      <div className="flex flex-col gap-[18px]">
        <ProfessorForm onMudou={recarregar} />
        <AtribuicaoSeries professores={professores} salas={salas} onMudou={recarregar} />
        <ListaProfessores professores={professores} salas={salas} onMudou={recarregar} />
      </div>
    </AppShell>
  );
}

// --------------------------------------------------------------------------- //
function ProfessorForm({ onMudou }: { onMudou: () => Promise<void> }) {
  const toast = useToast();
  const [nome, setNome] = useState("");
  const [telefone, setTelefone] = useState("");
  const [senha, setSenha] = useState("");

  async function cadastrar(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim() || !telefone.trim()) return;
    try {
      await cadastrarProfessor(nome.trim(), telefone.trim(), senha);
      setNome("");
      setTelefone("");
      setSenha("");
      await onMudou();
      toast({ tone: "success", title: "Professor cadastrado." });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao cadastrar professor.",
      });
    }
  }

  return (
    <Card>
      <CardHeader title="Cadastrar professor" />
      <form onSubmit={cadastrar} className="flex flex-wrap gap-2">
        <Input
          className="flex-1 min-w-[180px]"
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          placeholder="Nome do professor"
        />
        <Input
          className="w-52"
          value={telefone}
          onChange={(e) => setTelefone(e.target.value)}
          placeholder="WhatsApp, ex.: +5511999990000"
        />
        <Input
          className="w-44"
          type="password"
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
          placeholder="Senha do mural (opcional)"
        />
        <Button size="sm" type="submit" leftIcon={<PlusIcon size={15} />}>
          Cadastrar
        </Button>
      </form>
      <p className="mt-2 text-xs text-n-400">
        A senha habilita o login do professor no mural (em <strong>/professor</strong>). Atribua
        o professor às séries no card abaixo — um professor pode conduzir várias séries.
      </p>
    </Card>
  );
}

// --------------------------------------------------------------------------- //
// Atribuição: para cada série, escolhe o professor responsável (Sala.professor_id).
function AtribuicaoSeries({
  professores,
  salas,
  onMudou,
}: {
  professores: Professor[];
  salas: Sala[];
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();

  async function definir(salaId: string, professorId: string) {
    try {
      await definirProfessorDaSala(salaId, professorId || null);
      await onMudou();
      toast({ tone: "success", title: "Professor da série atualizado." });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao atualizar a série.",
      });
    }
  }

  return (
    <Card>
      <CardHeader title="Professor responsável por série" />
      {salas.length === 0 ? (
        <p className="text-sm text-n-500">
          Cadastre uma série em <strong>Salas e pais</strong> para atribuir um professor.
        </p>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Série</Th>
                <Th>Professor responsável</Th>
              </tr>
            </thead>
            <tbody>
              {salas.map((s) => (
                <Tr key={s.id}>
                  <Td className="font-medium">{s.nome}</Td>
                  <Td>
                    <Select
                      className="w-64"
                      value={s.professor_id ?? ""}
                      onChange={(e) => definir(s.id, e.target.value)}
                      disabled={professores.length === 0}
                    >
                      <option value="">— Sem professor —</option>
                      {professores.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.nome}
                        </option>
                      ))}
                    </Select>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      )}
      {professores.length === 0 && salas.length > 0 && (
        <p className="mt-2 text-xs text-n-400">Cadastre um professor acima para poder atribuí-lo.</p>
      )}
    </Card>
  );
}

// --------------------------------------------------------------------------- //
function ListaProfessores({
  professores,
  salas,
  onMudou,
}: {
  professores: Professor[];
  salas: Sala[];
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [editando, setEditando] = useState<Professor | null>(null);
  const [excluindo, setExcluindo] = useState<Professor | null>(null);

  function seriesDe(professorId: string): string[] {
    return salas.filter((s) => s.professor_id === professorId).map((s) => s.nome);
  }

  async function confirmarExclusao() {
    if (!excluindo) return;
    try {
      await removerProfessor(excluindo.id);
      setExcluindo(null);
      await onMudou();
      toast({ tone: "success", title: "Professor excluído." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao excluir." });
    }
  }

  return (
    <Card>
      <CardHeader title={`Professores (${professores.length})`} />
      {professores.length === 0 ? (
        <p className="text-sm text-n-500">Nenhum professor cadastrado ainda.</p>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Nome</Th>
                <Th>WhatsApp</Th>
                <Th>Séries</Th>
                <Th className="text-right">Ações</Th>
              </tr>
            </thead>
            <tbody>
              {professores.map((p) => {
                const series = seriesDe(p.id);
                return (
                  <Tr key={p.id}>
                    <Td className="font-medium">{p.nome}</Td>
                    <Td className="font-mono text-xs text-n-600">{p.telefone}</Td>
                    <Td className="text-xs text-n-600">
                      {series.length === 0 ? (
                        <span className="text-n-400">—</span>
                      ) : (
                        series.join(", ")
                      )}
                    </Td>
                    <Td className="text-right">
                      <div className="flex justify-end gap-1.5">
                        <Button size="sm" variant="secondary" onClick={() => setEditando(p)}>
                          Editar
                        </Button>
                        <Button size="sm" variant="danger" onClick={() => setExcluindo(p)}>
                          Excluir
                        </Button>
                      </div>
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
        </TableWrap>
      )}

      {editando && (
        <EditarProfessor
          professor={editando}
          onClose={() => setEditando(null)}
          onMudou={onMudou}
        />
      )}

      <ConfirmDialog
        open={excluindo !== null}
        onClose={() => setExcluindo(null)}
        onConfirm={confirmarExclusao}
        title="Excluir professor"
        message={
          excluindo
            ? `Excluir “${excluindo.nome}”? As séries que ele conduz ficarão sem professor.`
            : ""
        }
      />
    </Card>
  );
}

// --------------------------------------------------------------------------- //
function EditarProfessor({
  professor,
  onClose,
  onMudou,
}: {
  professor: Professor;
  onClose: () => void;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [nome, setNome] = useState(professor.nome);
  const [telefone, setTelefone] = useState(professor.telefone);
  const [senha, setSenha] = useState("");

  async function salvar() {
    if (!nome.trim() || !telefone.trim()) return;
    try {
      // Senha em branco mantém a atual; preenchida, redefine o acesso ao mural.
      await atualizarProfessor(
        professor.id,
        nome.trim(),
        telefone.trim(),
        senha ? senha : undefined
      );
      onClose();
      await onMudou();
      toast({ tone: "success", title: "Professor atualizado." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao salvar." });
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Editar professor"
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
        <Input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Nome" />
        <Input
          value={telefone}
          onChange={(e) => setTelefone(e.target.value)}
          placeholder="WhatsApp, ex.: +5511999990000"
        />
        <Input
          type="password"
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
          placeholder="Nova senha do mural (deixe em branco para manter)"
        />
        <p className="text-xs text-n-400">
          {professor.tem_acesso
            ? "Este professor já tem acesso ao mural."
            : "Defina uma senha para habilitar o acesso ao mural."}
        </p>
      </div>
    </Modal>
  );
}
