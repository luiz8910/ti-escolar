"use client";

/**
 * Equipe da secretaria — as contas que atendem os responsáveis (§6j).
 *
 * Até aqui só existia a API: criar uma funcionária exigia bater no endpoint à mão. Com a
 * fila de atendimento humano isso deixou de ser aceitável — não dá para pedir que alguém
 * atenda sem ter como cadastrar essa pessoa.
 *
 * "Excluir" não existe de propósito: quem sai é **desativada**. A conta desligada perde
 * o acesso na requisição seguinte (o back-end revalida o usuário a cada chamada), mas o
 * registro de quem respondeu o quê a qual responsável continua de pé.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  atualizarUsuario,
  criarUsuario,
  exigeEscolhaDeEscola,
  getSessao,
  listarUsuarios,
  logout,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/form";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

export default function EquipeDaSecretaria() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [itens, setItens] = useState<Usuario[]>([]);
  const [criando, setCriando] = useState(false);
  const [editando, setEditando] = useState<Usuario | null>(null);
  const toast = useToast();

  const recarregar = useCallback(async () => {
    setItens(await listarUsuarios());
  }, []);

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
    recarregar().catch(() =>
      toast({ tone: "danger", title: "Falha ao carregar a equipe." }),
    );
  }, [router, recarregar, toast]);

  async function alternarAtivo(alvo: Usuario) {
    try {
      await atualizarUsuario(alvo.id, { ativo: !(alvo.ativo ?? true) });
      await recarregar();
      toast({
        tone: "success",
        title: alvo.ativo ?? true ? "Acesso desativado." : "Acesso reativado.",
      });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha." });
    }
  }

  if (!usuario) return null;

  return (
    <AppShell
      title="Equipe da secretaria"
      user={{
        name: usuario.nome,
        role: usuario.papel === "super_admin" ? "Super Admin" : "Admin da escola",
      }}
      isSuperAdmin={usuario.papel === "super_admin"}
      onLogout={() => {
        logout();
        router.replace("/admin/login");
      }}
    >
      <Card>
        <CardHeader
          title={`Contas (${itens.length})`}
          action={<Button onClick={() => setCriando(true)}>Nova conta</Button>}
        />
        <p className="mb-3 text-sm text-n-500">
          Quem entra no painel e atende os responsáveis na fila de atendimento. Desativar
          uma conta corta o acesso imediatamente e preserva o histórico do que ela
          respondeu.
        </p>

        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Nome</Th>
                <Th>E-mail</Th>
                <Th>Papel</Th>
                <Th>Situação</Th>
                <Th className="text-right">Ações</Th>
              </tr>
            </thead>
            <tbody>
              {itens.map((u) => {
                const ativo = u.ativo ?? true;
                return (
                  <Tr key={u.id}>
                    <Td className="font-semibold">{u.nome}</Td>
                    <Td className="text-n-600">{u.email}</Td>
                    <Td>
                      <Badge tone={u.papel === "super_admin" ? "brand" : "neutral"}>
                        {u.papel === "super_admin" ? "Super admin" : "Secretaria"}
                      </Badge>
                    </Td>
                    <Td>
                      <Badge tone={ativo ? "success" : "neutral"}>
                        {ativo ? "Ativa" : "Desativada"}
                      </Badge>
                    </Td>
                    <Td className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button variant="ghost" onClick={() => setEditando(u)}>
                          Editar
                        </Button>
                        {u.id !== usuario.id && (
                          <Button variant="secondary" onClick={() => alternarAtivo(u)}>
                            {ativo ? "Desativar" : "Reativar"}
                          </Button>
                        )}
                      </div>
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
        </TableWrap>
      </Card>

      {criando && (
        <ModalNovaConta
          onFechar={() => setCriando(false)}
          onSalvo={async () => {
            setCriando(false);
            await recarregar();
            toast({ tone: "success", title: "Conta criada." });
          }}
        />
      )}

      {editando && (
        <ModalEditarConta
          alvo={editando}
          onFechar={() => setEditando(null)}
          onSalvo={async () => {
            setEditando(null);
            await recarregar();
            toast({ tone: "success", title: "Conta atualizada." });
          }}
        />
      )}
    </AppShell>
  );
}

function ModalNovaConta({
  onFechar,
  onSalvo,
}: {
  onFechar: () => void;
  onSalvo: () => Promise<void>;
}) {
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    setSalvando(true);
    setErro("");
    try {
      await criarUsuario({ nome: nome.trim(), email: email.trim(), senha });
      await onSalvo();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Falha ao criar a conta.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal open title="Nova conta da secretaria" onClose={onFechar}>
      <form onSubmit={salvar} className="flex flex-col gap-3">
        <Field label="Nome">
          <Input value={nome} onChange={(e) => setNome(e.target.value)} required />
        </Field>
        <Field label="E-mail" hint="É com ele que a pessoa entra no painel.">
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </Field>
        <Field label="Senha">
          <Input
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            required
            minLength={8}
          />
        </Field>
        {erro && <p className="text-[12.5px] text-danger">{erro}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onFechar}>
            Cancelar
          </Button>
          <Button type="submit" disabled={salvando}>
            {salvando ? "Criando…" : "Criar conta"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function ModalEditarConta({
  alvo,
  onFechar,
  onSalvo,
}: {
  alvo: Usuario;
  onFechar: () => void;
  onSalvo: () => Promise<void>;
}) {
  const [nome, setNome] = useState(alvo.nome);
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    setSalvando(true);
    setErro("");
    try {
      // Senha em branco = manter a atual; o back-end trata o campo ausente como "não mexer".
      await atualizarUsuario(alvo.id, {
        nome: nome.trim(),
        ...(senha ? { senha } : {}),
      });
      await onSalvo();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Falha ao atualizar a conta.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal open title={`Editar ${alvo.email}`} onClose={onFechar}>
      <form onSubmit={salvar} className="flex flex-col gap-3">
        <Field label="Nome">
          <Input value={nome} onChange={(e) => setNome(e.target.value)} required />
        </Field>
        <Field label="Nova senha" hint="Deixe em branco para manter a senha atual.">
          <Input
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            minLength={8}
          />
        </Field>
        {erro && <p className="text-[12.5px] text-danger">{erro}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onFechar}>
            Cancelar
          </Button>
          <Button type="submit" disabled={salvando}>
            {salvando ? "Salvando…" : "Salvar"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
