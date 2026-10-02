"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  adicionarContato,
  atualizarGrupo,
  consultarQuota,
  Contato,
  criarGrupo,
  enviarParaGrupo,
  exigeEscolhaDeEscola,
  getSessao,
  Grupo,
  logout,
  listarGrupos,
  listarTemplates,
  OrigemParametro,
  ParametroDisparo,
  placeholdersDoCorpo,
  Quota,
  removerContatoDoGrupo,
  removerGrupo,
  ResultadoEnvioGrupo,
  TemplateMensagem,
  trechoDoPlaceholder,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { QuotaBar } from "@/components/layout/QuotaBar";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { CampoTelefone } from "@/components/ui/campos";
import { TableWrap, Table, Th, Td, Tr } from "@/components/ui/Table";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import { PencilIcon, PlusIcon, TrashIcon, UsersIcon } from "@/components/ui/icons";
import { formatarTelefone } from "@/lib/mascaras";

export default function AdminDashboard() {
  const router = useRouter();
  const toast = useToast();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [grupos, setGrupos] = useState<Grupo[]>([]);
  const [quota, setQuota] = useState<Quota | null>(null);
  const [selecionado, setSelecionado] = useState<Grupo | null>(null);

  const recarregar = useCallback(async () => {
    const [gs, q] = await Promise.all([listarGrupos(), consultarQuota()]);
    setGrupos(gs);
    setQuota(q);
    setSelecionado((atual) => (atual ? gs.find((g) => g.id === atual.id) ?? null : null));
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
    recarregar().catch(() => toast({ tone: "danger", title: "Falha ao carregar dados." }));
  }, [router, recarregar, toast]);

  function sair() {
    logout();
    router.replace("/admin/login");
  }

  if (!usuario) return null;

  return (
    <AppShell
      title="Grupos & disparos"
      user={{
        name: usuario.nome,
        role: usuario.papel === "super_admin" ? "Super Admin" : "Admin da escola",
      }}
      isSuperAdmin={usuario.papel === "super_admin"}
      onLogout={sair}
    >
      <div className="flex flex-col gap-[18px]">
        {quota && (
          <QuotaBar
            enviados={quota.enviados}
            limite={quota.limite_diario}
            proximaLiberacao={quota.proxima_liberacao}
          />
        )}

        <div className="grid grid-cols-1 gap-[18px] lg:grid-cols-[300px_1fr]">
          <GruposPanel
            grupos={grupos}
            selecionado={selecionado}
            onSelecionar={setSelecionado}
            onCriado={recarregar}
          />
          <GrupoDetalhe grupo={selecionado} onMudou={recarregar} />
        </div>
      </div>
    </AppShell>
  );
}

/** "1 contato", "2 contatos" — a tela dizia "Enviar para 1 contatos". */
function plural(n: number, um: string, varios: string): string {
  return `${n} ${n === 1 ? um : varios}`;
}

function GruposPanel({
  grupos,
  selecionado,
  onSelecionar,
  onCriado,
}: {
  grupos: Grupo[];
  selecionado: Grupo | null;
  onSelecionar: (g: Grupo) => void;
  onCriado: () => Promise<void>;
}) {
  const toast = useToast();
  const [novo, setNovo] = useState("");
  const [criando, setCriando] = useState(false);

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    if (criando || !novo.trim()) return;
    setCriando(true);
    try {
      await criarGrupo(novo.trim(), "");
      setNovo("");
      await onCriado();
      toast({ tone: "success", title: "Grupo criado." });
    } catch (err) {
      // O servidor diz o motivo (nome repetido, por exemplo); "não foi possível" sozinho
      // deixava a secretaria tentando de novo o mesmo nome.
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Não foi possível criar o grupo.",
      });
    } finally {
      setCriando(false);
    }
  }

  return (
    <Card className="flex flex-col">
      <CardHeader title="Grupos" count={grupos.length} />
      <div className="flex flex-col gap-1">
        {grupos.map((g) => {
          const active = selecionado?.id === g.id;
          return (
            <button
              key={g.id}
              onClick={() => onSelecionar(g)}
              className={
                "flex items-center justify-between rounded-[10px] px-3 py-2.5 text-left text-[13px] font-semibold " +
                (active ? "bg-brand-600 text-white" : "text-n-700 hover:bg-n-50")
              }
            >
              <span>{g.nome}</span>
              <span
                className={
                  "rounded-full px-2 py-0.5 text-[11px] font-bold " +
                  (active ? "bg-white/20" : "bg-n-100 text-n-500")
                }
              >
                {g.total_membros}
              </span>
            </button>
          );
        })}
        {grupos.length === 0 && (
          <p className="px-3 py-2 text-sm text-n-400">Nenhum grupo ainda.</p>
        )}
      </div>
      <form onSubmit={criar} className="mt-auto flex gap-2 border-t border-n-100 pt-3.5">
        <Input value={novo} onChange={(e) => setNovo(e.target.value)} placeholder="Novo grupo…" />
        <Button size="sm" type="submit" loading={criando} leftIcon={<PlusIcon size={15} />}>
          Criar
        </Button>
      </form>
    </Card>
  );
}

function GrupoDetalhe({
  grupo,
  onMudou,
}: {
  grupo: Grupo | null;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [nome, setNome] = useState("");
  const [telefone, setTelefone] = useState("");
  const [titulo, setTitulo] = useState("");
  const [templates, setTemplates] = useState<TemplateMensagem[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [parametros, setParametros] = useState<ParametroDisparo[]>([]);
  const [resultado, setResultado] = useState<ResultadoEnvioGrupo | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [adicionando, setAdicionando] = useState(false);
  const [salvandoContato, setSalvandoContato] = useState(false);
  const [editando, setEditando] = useState(false);
  const [excluindoGrupo, setExcluindoGrupo] = useState(false);
  const [removendo, setRemovendo] = useState<Contato | null>(null);

  // Só os aprovados **na conta desta escola**: quem decide isso é o servidor, que conhece
  // o vínculo escola → conta. Oferecer os demais seria convidar a um disparo que a Graph
  // API recusa depois de a cota ter sido consumida.
  const enviaveis = useMemo(() => templates.filter((t) => t.enviavel_aqui), [templates]);
  const template = useMemo(
    () => enviaveis.find((t) => t.id === templateId) ?? null,
    [enviaveis, templateId]
  );

  useEffect(() => {
    listarTemplates()
      .then(setTemplates)
      .catch(() => {
        /* sem catálogo a tela ainda serve para gerir contatos */
      });
  }, []);

  // Trocar de template zera os campos: o número de variáveis muda, e reaproveitar os
  // valores antigos entregaria o texto de um `{{n}}` no lugar de outro.
  useEffect(() => {
    if (!template) {
      setParametros([]);
      return;
    }
    setParametros(
      placeholdersDoCorpo(template.corpo).map((n) => ({
        // O primeiro `{{n}}` é quase sempre a saudação — mas o palpite é só um default
        // visível, que a secretaria vê e troca, não uma regra escondida como a de antes.
        origem: n === 1 ? "responsavel" : "texto",
        texto: "",
      }))
    );
  }, [template]);

  if (!grupo) {
    return (
      <Card className="flex items-center justify-center">
        <EmptyState
          icon={<UsersIcon size={24} />}
          title="Selecione um grupo"
          description="Escolha um grupo à esquerda para gerenciar contatos e enviar mensagens."
        />
      </Card>
    );
  }

  async function addContato(e: React.FormEvent) {
    e.preventDefault();
    if (salvandoContato || !nome.trim() || !telefone.trim()) return;
    setSalvandoContato(true);
    try {
      await adicionarContato(grupo!.id, nome.trim(), telefone.trim());
      setNome("");
      setTelefone("");
      setAdicionando(false);
      await onMudou();
      toast({ tone: "success", title: "Contato adicionado." });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao adicionar contato.",
      });
    } finally {
      setSalvandoContato(false);
    }
  }

  async function confirmarRemocaoDoContato() {
    if (!removendo) return;
    const contato = removendo;
    setRemovendo(null);
    try {
      await removerContatoDoGrupo(grupo!.id, contato.id);
      await onMudou();
      toast({ tone: "success", title: `${contato.nome} saiu do grupo.` });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao remover o contato.",
      });
    }
  }

  async function confirmarExclusaoDoGrupo() {
    setExcluindoGrupo(false);
    try {
      await removerGrupo(grupo!.id);
      await onMudou();
      toast({ tone: "success", title: "Grupo excluído." });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao excluir o grupo.",
      });
    }
  }

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (!titulo.trim() || !template) return;
    const faltando = parametros.some((p) => p.origem === "texto" && !p.texto.trim());
    if (faltando) {
      toast({ tone: "danger", title: "Preencha todos os campos do template." });
      return;
    }
    setEnviando(true);
    setResultado(null);
    try {
      const r = await enviarParaGrupo(grupo!.id, titulo.trim(), template.id, parametros);
      setResultado(r);
      setTitulo("");
      setParametros((atuais) => atuais.map((p) => ({ ...p, texto: "" })));
      await onMudou();
      // Cancelado por outra tela enquanto saía: dizer "concluído" esconderia que parte
      // do grupo não recebeu.
      const cancelado = r.broadcast.status === "cancelado";
      toast({
        tone: cancelado ? "info" : "success",
        title: cancelado ? "Disparo cancelado durante o envio." : "Disparo concluído.",
        description: `${plural(r.broadcast.enviados, "enviado", "enviados")} · ${r.broadcast.restante_cota} restantes na cota.`,
      });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao enviar." });
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title={
          <>
            {grupo.nome}{" "}
            <span className="font-semibold text-n-400">· {plural(grupo.total_membros, "contato", "contatos")}</span>
          </>
        }
        action={
          <div className="flex flex-wrap justify-end gap-1.5">
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<PlusIcon size={14} />}
              onClick={() => setAdicionando((v) => !v)}
            >
              Contato
            </Button>
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<PencilIcon size={14} />}
              onClick={() => setEditando(true)}
            >
              Editar
            </Button>
            <Button
              variant="danger"
              size="sm"
              leftIcon={<TrashIcon size={14} />}
              onClick={() => setExcluindoGrupo(true)}
            >
              Excluir
            </Button>
          </div>
        }
      />
      {grupo.descricao && <p className="-mt-2 mb-3 text-xs text-n-500">{grupo.descricao}</p>}

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
            {grupo.membros.map((c) => (
              <Tr key={c.id}>
                <Td className="font-medium">{c.nome}</Td>
                <Td className="font-mono text-xs text-n-500">{formatarTelefone(c.telefone)}</Td>
                <Td className="text-right">
                  <Button size="sm" variant="danger" onClick={() => setRemovendo(c)}>
                    Remover
                  </Button>
                </Td>
              </Tr>
            ))}
            {grupo.membros.length === 0 && (
              <Tr>
                <Td colSpan={3} className="text-n-400">
                  Sem contatos neste grupo.
                </Td>
              </Tr>
            )}
          </tbody>
        </Table>
      </TableWrap>

      {adicionando && (
        <form onSubmit={addContato} className="mt-3.5 flex flex-wrap gap-2">
          <Input
            className="flex-1"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder="Nome do responsável"
          />
          <CampoTelefone
            className="w-44"
            mono
            value={telefone}
            onChange={setTelefone}
          />
          <Button variant="secondary" size="sm" type="submit" loading={salvandoContato}>
            Adicionar
          </Button>
        </form>
      )}

      <div className="mt-[18px] border-t border-n-100 pt-4">
        <h4 className="text-sm font-bold text-n-900">Enviar mensagem ao grupo</h4>
        <p className="mt-1 text-xs text-n-500">
          Sai por um <b>template aprovado</b> e respeita a cota diária. Alcança apenas os{" "}
          {grupo.total_membros} contato(s) de <b>{grupo.nome}</b>. O texto variável entra
          nos campos abaixo — é o que muda a cada disparo sem exigir nova aprovação.
        </p>
        {enviaveis.length === 0 ? (
          <p className="mt-3 rounded-md bg-warning-soft p-3 text-[13px] text-warning">
            Nenhum template aprovado para esta escola. Fora da janela de 24h o WhatsApp só
            entrega template aprovado pela Meta — crie um em <b>Templates de mensagem</b> e
            aguarde a revisão.
          </p>
        ) : (
          <form onSubmit={enviar} className="mt-3 flex flex-col gap-2.5">
            <Input
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder="Título do disparo (só para o histórico)"
            />
            <Select value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
              <option value="">Escolha o template aprovado…</option>
              {enviaveis.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.nome}
                  {t.categoria === "marketing" ? " (marketing — mais caro)" : ""}
                </option>
              ))}
            </Select>

            {template && (
              <>
                <p className="rounded-md bg-n-50 p-2.5 font-mono text-[11.5px] leading-relaxed text-n-600">
                  {template.corpo}
                </p>
                {parametros.map((p, i) => {
                  const numero = i + 1;
                  return (
                    <div key={numero} className="flex flex-wrap items-start gap-2">
                      <div className="w-full text-[11.5px] text-n-500">
                        <b className="font-mono">{`{{${numero}}}`}</b>{" "}
                        {trechoDoPlaceholder(template.corpo, numero)}
                      </div>
                      <Select
                        className="w-[190px]"
                        value={p.origem}
                        onChange={(e) =>
                          setParametros((atuais) =>
                            atuais.map((atual, j) =>
                              j === i
                                ? { ...atual, origem: e.target.value as OrigemParametro }
                                : atual
                            )
                          )
                        }
                      >
                        <option value="responsavel">Nome do responsável</option>
                        <option value="escola">Nome da escola</option>
                        <option value="texto">Texto que eu escrever</option>
                      </Select>
                      {p.origem === "texto" && (
                        <Textarea
                          className="min-w-[220px] flex-1"
                          rows={2}
                          value={p.texto}
                          onChange={(e) =>
                            setParametros((atuais) =>
                              atuais.map((atual, j) =>
                                j === i ? { ...atual, texto: e.target.value } : atual
                              )
                            )
                          }
                          placeholder="Ex.: a reunião de pais será dia 20/08, às 15h."
                        />
                      )}
                    </div>
                  );
                })}
              </>
            )}

            <Button
              type="submit"
              loading={enviando}
              disabled={!template}
              className="self-start"
            >
              {enviando
                ? "Enviando…"
                : `Enviar para ${plural(grupo.total_membros, "contato", "contatos")}`}
            </Button>
          </form>
        )}

        {resultado && (
          <div className="mt-4 rounded-md bg-success-soft p-3 text-[13px] text-success">
            {resultado.broadcast.status === "cancelado"
              ? "Disparo cancelado durante o envio"
              : "✓ Disparo concluído"}{" "}
            — <b>{resultado.broadcast.enviados}</b>{" "}
            {resultado.broadcast.enviados === 1 ? "enviado" : "enviados"}
            {resultado.broadcast.falhas > 0 && `, ${resultado.broadcast.falhas} falhas`}
            {resultado.broadcast.bloqueados_por_limite > 0 &&
              `, ${resultado.broadcast.bloqueados_por_limite} bloqueados pela cota`}
            . Restam {resultado.broadcast.restante_cota} na cota de hoje.
          </div>
        )}
      </div>

      {editando && (
        <EditarGrupoModal grupo={grupo} onClose={() => setEditando(false)} onMudou={onMudou} />
      )}

      <ConfirmDialog
        open={excluindoGrupo}
        onClose={() => setExcluindoGrupo(false)}
        onConfirm={confirmarExclusaoDoGrupo}
        title={`Excluir grupo — ${grupo.nome}`}
        message={
          "O grupo deixa de existir e não poderá mais receber disparos. " +
          (grupo.total_membros > 0
            ? `${plural(grupo.total_membros, "contato continua", "contatos continuam")} ` +
              "em Responsáveis, e os "
            : "Os ") +
          "disparos já feitos continuam no histórico."
        }
      />

      <ConfirmDialog
        open={removendo !== null}
        onClose={() => setRemovendo(null)}
        onConfirm={confirmarRemocaoDoContato}
        title="Remover do grupo"
        confirmLabel="Remover"
        message={
          removendo
            ? `${removendo.nome} deixa de receber os disparos de “${grupo.nome}”, mas ` +
              `continua cadastrado em Responsáveis.`
            : ""
        }
      />
    </Card>
  );
}

/** Nome e descrição do grupo. Os contatos são geridos na lista, não aqui. */
function EditarGrupoModal({
  grupo,
  onClose,
  onMudou,
}: {
  grupo: Grupo;
  onClose: () => void;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [nome, setNome] = useState(grupo.nome);
  const [descricao, setDescricao] = useState(grupo.descricao);
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function salvar(e?: React.FormEvent) {
    e?.preventDefault();
    if (salvando) return;
    if (!nome.trim()) {
      setErro("Informe o nome do grupo.");
      return;
    }
    setSalvando(true);
    setErro("");
    try {
      await atualizarGrupo(grupo.id, nome.trim(), descricao.trim());
      onClose();
      await onMudou();
      toast({ tone: "success", title: "Grupo atualizado." });
    } catch (err) {
      // Nome repetido é o erro comum: fica no formulário, para corrigir sem reabrir.
      setErro(err instanceof Error ? err.message : "Falha ao salvar o grupo.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Editar grupo"
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
        <Field label="Nome" htmlFor="grupo-nome">
          <Input
            id="grupo-nome"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            autoFocus
          />
        </Field>
        <Field label="Descrição (opcional)" htmlFor="grupo-descricao">
          <Textarea
            id="grupo-descricao"
            value={descricao}
            onChange={(e) => setDescricao(e.target.value)}
            rows={2}
          />
        </Field>
        {erro && (
          <p className="rounded-lg bg-danger-soft px-3 py-2 text-[12.5px] text-danger">{erro}</p>
        )}
        {/* Enter no campo salva; os botões ficam no rodapé do modal. */}
        <button type="submit" className="hidden" aria-hidden tabIndex={-1} />
      </form>
    </Modal>
  );
}
