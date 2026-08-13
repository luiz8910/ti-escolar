"use client";

/**
 * Equipe da escola — as contas que entram no painel e atendem os responsáveis (§6j).
 *
 * Até 12/ago/2026 a tela tratava todo mundo como "secretaria". O apontamento pediu os
 * postos reais — diretor, vice-diretor, coordenador e secretaria — **com hierarquia**:
 * cada pessoa só gerencia quem está estritamente abaixo dela, e a secretaria não gerencia
 * ninguém.
 *
 * A tela **espelha** essa regra (só oferece cargos abaixo do seu, esconde os botões em
 * quem você não pode tocar), mas quem a impõe é o back-end. O filtro aqui é conveniência,
 * não segurança: um `PUT` direto continua sendo recusado.
 *
 * "Excluir" não existe de propósito: quem sai é **desativada**. A conta desligada perde o
 * acesso na requisição seguinte (o back-end revalida o usuário a cada chamada), mas o
 * registro de quem respondeu o quê a qual responsável continua de pé.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  atualizarUsuario,
  Cargo,
  CARGOS,
  criarUsuario,
  exigeEscolhaDeEscola,
  getSessao,
  listarUsuarios,
  logout,
  nivelDoCargo,
  Turno,
  TURNOS,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/form";
import { CampoTelefone } from "@/components/ui/campos";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

/** O nível de quem está logado — super admin fica acima de qualquer cargo. */
function nivelDe(u: Usuario): number {
  return u.papel === "super_admin" ? 99 : nivelDoCargo(u.cargo);
}

/** Cargos que este usuário pode atribuir: só os estritamente abaixo do dele. */
function cargosDisponiveis(eu: Usuario): typeof CARGOS {
  const meu = nivelDe(eu);
  return CARGOS.filter((c) => c.nivel < meu);
}

/** Posso gerenciar esta conta? Mesma regra do `manda_em` do domínio. */
function mandaEm(eu: Usuario, alvo: Usuario): boolean {
  if (eu.papel === "super_admin") return true;
  if (alvo.papel === "super_admin") return false;
  return nivelDe(eu) > nivelDe(alvo);
}

export default function EquipeDaEscola() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [itens, setItens] = useState<Usuario[]>([]);
  const [criando, setCriando] = useState(false);
  const [editando, setEditando] = useState<Usuario | null>(null);
  // Conta a destacar, vinda de `?u=` — é como a auditoria (§13) chega aqui a partir do
  // nome de quem fez a ação. Lida do `location` e não de `useSearchParams` para não
  // arrastar a tela inteira para uma fronteira de Suspense por causa de um realce.
  const [destaque, setDestaque] = useState("");
  const toast = useToast();

  const recarregar = useCallback(async () => {
    setItens(await listarUsuarios());
  }, []);

  useEffect(() => {
    setDestaque(new URLSearchParams(window.location.search).get("u") ?? "");
  }, []);

  // Rola até a conta destacada depois que a lista chega. Numa escola com trinta contas,
  // realçar uma linha fora da dobra não ajudaria ninguém.
  useEffect(() => {
    if (!destaque || itens.length === 0) return;
    document
      .getElementById(`usuario-${destaque}`)
      ?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [destaque, itens]);

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

  // A secretaria abre a tela e vê a equipe, mas não cadastra nem edita ninguém além de si.
  const podeGerenciar = usuario.papel !== "secretaria";
  const disponiveis = cargosDisponiveis(usuario);

  return (
    <AppShell
      title="Equipe da escola"
      user={{
        name: usuario.nome,
        role:
          usuario.papel === "super_admin"
            ? "Super Admin"
            : usuario.cargo_rotulo || "Admin da escola",
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
          action={
            podeGerenciar && disponiveis.length > 0 ? (
              <Button onClick={() => setCriando(true)}>Nova conta</Button>
            ) : undefined
          }
        />
        <p className="mb-3 text-sm text-n-500">
          Quem entra no painel e atende os responsáveis na fila de atendimento. Cada pessoa
          só gerencia contas de <b>cargo abaixo do seu</b>; a secretaria não gerencia
          contas. Desativar corta o acesso imediatamente e preserva o histórico do que a
          pessoa respondeu.
        </p>

        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Nome</Th>
                <Th>E-mail</Th>
                <Th>Cargo</Th>
                <Th>Contato</Th>
                <Th>Situação</Th>
                <Th className="text-right">Ações</Th>
              </tr>
            </thead>
            <tbody>
              {itens.map((u) => {
                const ativo = u.ativo ?? true;
                const proprio = u.id === usuario.id;
                // Editar a própria conta (nome, senha, contato) é sempre permitido.
                const podeEditar = proprio || mandaEm(usuario, u);
                return (
                  <Tr
                    key={u.id}
                    id={`usuario-${u.id}`}
                    className={
                      u.id === destaque ? "bg-brand-50 ring-2 ring-inset ring-brand-500" : ""
                    }
                  >
                    <Td className="font-semibold">
                      {u.nome}
                      {proprio && (
                        <span className="ml-1.5 text-[11px] font-semibold text-n-400">
                          você
                        </span>
                      )}
                    </Td>
                    <Td className="text-n-600">{u.email}</Td>
                    <Td>
                      {u.papel === "super_admin" ? (
                        <Badge tone="brand">Super admin</Badge>
                      ) : (
                        <Badge tone={u.papel === "secretaria" ? "neutral" : "brand"}>
                          {u.cargo_rotulo || "—"}
                        </Badge>
                      )}
                    </Td>
                    <Td className="text-xs text-n-600">
                      {u.telefone || <span className="text-n-400">—</span>}
                      {u.turno && (
                        <span className="ml-1.5 text-n-400">
                          · {TURNOS.find((t) => t.valor === u.turno)?.rotulo}
                        </span>
                      )}
                    </Td>
                    <Td>
                      <Badge tone={ativo ? "success" : "neutral"}>
                        {ativo ? "Ativa" : "Desativada"}
                      </Badge>
                    </Td>
                    <Td className="text-right">
                      <div className="flex justify-end gap-2">
                        {podeEditar && (
                          <Button variant="ghost" onClick={() => setEditando(u)}>
                            Editar
                          </Button>
                        )}
                        {!proprio && mandaEm(usuario, u) && (
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
          cargos={disponiveis}
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
          eu={usuario}
          cargos={disponiveis}
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

/** Campos de contato e lotação, compartilhados pelos dois modais. */
function CamposContato({
  telefone,
  setTelefone,
  endereco,
  setEndereco,
  turno,
  setTurno,
}: {
  telefone: string;
  setTelefone: (v: string) => void;
  endereco: string;
  setEndereco: (v: string) => void;
  turno: Turno | "";
  setTurno: (v: Turno | "") => void;
}) {
  return (
    <>
      <Field
        label="WhatsApp"
        hint="Usado para avisar de um atendimento esperando na fila."
      >
        <CampoTelefone value={telefone} onChange={setTelefone} />
      </Field>
      <Field label="Endereço completo">
        <Input
          value={endereco}
          onChange={(e) => setEndereco(e.target.value)}
          placeholder="Rua, número, bairro, cidade"
        />
      </Field>
      <Field label="Turno">
        <Select value={turno} onChange={(e) => setTurno(e.target.value as Turno | "")}>
          <option value="">Não informado</option>
          {TURNOS.map((t) => (
            <option key={t.valor} value={t.valor}>
              {t.rotulo}
            </option>
          ))}
        </Select>
      </Field>
    </>
  );
}

function ModalNovaConta({
  cargos,
  onFechar,
  onSalvo,
}: {
  cargos: typeof CARGOS;
  onFechar: () => void;
  onSalvo: () => Promise<void>;
}) {
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  // O menor cargo disponível é o padrão: se errar, erra para menos privilégio.
  const [cargo, setCargo] = useState<Cargo>(cargos[cargos.length - 1].valor);
  const [telefone, setTelefone] = useState("");
  const [endereco, setEndereco] = useState("");
  const [turno, setTurno] = useState<Turno | "">("");
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    setSalvando(true);
    setErro("");
    try {
      await criarUsuario({
        nome: nome.trim(),
        email: email.trim(),
        senha,
        cargo,
        telefone,
        endereco,
        turno,
      });
      await onSalvo();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Falha ao criar a conta.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal open title="Nova conta da escola" onClose={onFechar}>
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
        <Field
          label="Cargo"
          hint="Só aparecem os cargos abaixo do seu. A secretaria não gerencia contas."
        >
          <Select value={cargo} onChange={(e) => setCargo(e.target.value as Cargo)}>
            {cargos.map((c) => (
              <option key={c.valor} value={c.valor}>
                {c.rotulo}
              </option>
            ))}
          </Select>
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
        <CamposContato
          telefone={telefone}
          setTelefone={setTelefone}
          endereco={endereco}
          setEndereco={setEndereco}
          turno={turno}
          setTurno={setTurno}
        />
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
  eu,
  cargos,
  onFechar,
  onSalvo,
}: {
  alvo: Usuario;
  eu: Usuario;
  cargos: typeof CARGOS;
  onFechar: () => void;
  onSalvo: () => Promise<void>;
}) {
  const [nome, setNome] = useState(alvo.nome);
  const [senha, setSenha] = useState("");
  const [cargo, setCargo] = useState<Cargo | "">(alvo.cargo);
  const [telefone, setTelefone] = useState(alvo.telefone);
  const [endereco, setEndereco] = useState(alvo.endereco);
  const [turno, setTurno] = useState<Turno | "">(alvo.turno);
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  // Ninguém troca o próprio cargo — promover-se é o ataque óbvio, e rebaixar-se sozinho
  // deixa a escola sem ninguém no topo. O super admin não ocupa cargo.
  const podeTrocarCargo =
    alvo.id !== eu.id && alvo.papel !== "super_admin" && cargos.length > 0;

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    setSalvando(true);
    setErro("");
    try {
      // Senha em branco = manter a atual; o back-end trata o campo ausente como "não mexer".
      await atualizarUsuario(alvo.id, {
        nome: nome.trim(),
        ...(senha ? { senha } : {}),
        ...(podeTrocarCargo && cargo ? { cargo } : {}),
        telefone,
        endereco,
        turno,
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
        {podeTrocarCargo ? (
          <Field label="Cargo" hint="Trocar o cargo troca junto o acesso ao painel.">
            <Select value={cargo} onChange={(e) => setCargo(e.target.value as Cargo)}>
              {/* O cargo atual entra na lista mesmo quando não é atribuível por você —
                  senão o select abriria mostrando outro cargo e trocaria sem querer. */}
              {!cargos.some((c) => c.valor === alvo.cargo) && alvo.cargo && (
                <option value={alvo.cargo}>{alvo.cargo_rotulo}</option>
              )}
              {cargos.map((c) => (
                <option key={c.valor} value={c.valor}>
                  {c.rotulo}
                </option>
              ))}
            </Select>
          </Field>
        ) : (
          <Field label="Cargo">
            <Input value={alvo.cargo_rotulo || "Super admin"} disabled />
          </Field>
        )}
        <Field label="Nova senha" hint="Deixe em branco para manter a senha atual.">
          <Input
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            minLength={8}
          />
        </Field>
        <CamposContato
          telefone={telefone}
          setTelefone={setTelefone}
          endereco={endereco}
          setEndereco={setEndereco}
          turno={turno}
          setTurno={setTurno}
        />
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
