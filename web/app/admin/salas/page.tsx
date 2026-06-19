"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  Aluno,
  atualizarPai,
  atualizarSala,
  cadastrarPai,
  CoberturaSala,
  coberturaDasSalas,
  criarSala,
  desvincularPaiDaSala,
  getSessao,
  listarAlunos,
  listarPais,
  listarSalas,
  logout,
  notificarProfessor,
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
import { Input, Select, Field, Textarea } from "@/components/ui/form";
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
  const [coberturas, setCoberturas] = useState<Record<string, CoberturaSala>>({});
  const [selecionada, setSelecionada] = useState<Sala | null>(null);
  const toast = useToast();

  const recarregar = useCallback(async () => {
    const [ss, ps, cobs] = await Promise.all([
      listarSalas(),
      listarPais(),
      coberturaDasSalas(),
    ]);
    setSalas(ss);
    setPais(ps);
    setCoberturas(Object.fromEntries(cobs.map((c) => [c.sala_id, c])));
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
            coberturas={coberturas}
            selecionada={selecionada}
            onSelecionar={setSelecionada}
            onMudou={recarregar}
          />
          <SalaDetalhe
            sala={selecionada}
            pais={pais}
            cobertura={selecionada ? coberturas[selecionada.id] ?? null : null}
            onMudou={recarregar}
          />
        </div>

        <PaisPanel pais={pais} onMudou={recarregar} />
      </div>
    </AppShell>
  );
}

// --------------------------------------------------------------------------- //
function SalasPanel({
  salas,
  coberturas,
  selecionada,
  onSelecionar,
  onMudou,
}: {
  salas: Sala[];
  coberturas: Record<string, CoberturaSala>;
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

  return (
    <Card className="flex flex-col">
      <CardHeader title="Salas (turmas)" count={salas.length} />
      <div className="flex flex-col gap-1">
        {salas.map((s) => {
          const active = selecionada?.id === s.id;
          const semContato = coberturas[s.id]?.total_sem_contato ?? 0;
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
                {semContato > 0 && (
                  <span
                    title={`${semContato} aluno(s) sem contato de responsável`}
                    className={
                      "rounded-full px-2 py-0.5 text-[11px] font-bold " +
                      (active ? "bg-white/20 text-white" : "bg-warning-soft text-warning")
                    }
                  >
                    ⚠ {semContato}
                  </span>
                )}
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

      {excluindo && (
        <ExcluirSalaModal
          sala={excluindo}
          salas={salas}
          onClose={() => setExcluindo(null)}
          onMudou={onMudou}
        />
      )}
    </Card>
  );
}

// --------------------------------------------------------------------------- //
function ExcluirSalaModal({
  sala,
  salas,
  onClose,
  onMudou,
}: {
  sala: Sala;
  salas: Sala[];
  onClose: () => void;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [alunos, setAlunos] = useState<Aluno[] | null>(null); // null = carregando
  const [estrategia, setEstrategia] = useState<"mover" | "excluir">("mover");
  const [destinoId, setDestinoId] = useState("");
  const [novaSerie, setNovaSerie] = useState("");
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    listarAlunos(sala.id)
      .then(setAlunos)
      .catch(() => {
        setAlunos([]);
        toast({ tone: "danger", title: "Falha ao verificar alunos da série." });
      });
  }, [sala.id, toast]);

  const total = alunos?.length ?? 0;
  const outras = salas.filter((s) => s.id !== sala.id);
  const criandoSerie = destinoId === "__nova__";

  async function confirmar() {
    setSalvando(true);
    try {
      if (total === 0 || estrategia === "excluir") {
        // Série vazia ou opção de excluir os alunos junto.
        await removerSala(sala.id);
      } else {
        // Mover os alunos para outra série (criando-a se necessário).
        let destino = destinoId;
        if (criandoSerie) {
          if (!novaSerie.trim()) {
            toast({ tone: "danger", title: "Informe o nome da nova série." });
            setSalvando(false);
            return;
          }
          destino = (await criarSala(novaSerie.trim())).id;
        }
        if (!destino) {
          toast({ tone: "danger", title: "Selecione a série destino." });
          setSalvando(false);
          return;
        }
        await removerSala(sala.id, destino);
      }
      onClose();
      await onMudou();
      toast({ tone: "success", title: "Série excluída." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao excluir." });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`Excluir série — ${sala.nome}`}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            variant="danger"
            size="sm"
            onClick={confirmar}
            loading={salvando}
            disabled={alunos === null}
          >
            Excluir série
          </Button>
        </>
      }
    >
      {alunos === null ? (
        <p className="text-sm text-n-400">Verificando alunos…</p>
      ) : total === 0 ? (
        <p className="text-[13px] text-n-600">
          A série “{sala.nome}” não tem alunos. Os pais/responsáveis continuam cadastrados.
        </p>
      ) : (
        <div className="flex flex-col gap-3 text-[13px]">
          <p className="text-n-600">
            A série “{sala.nome}” tem <strong>{total} aluno(s)</strong>. O que fazer com eles?
          </p>

          <label className="flex items-start gap-2 font-semibold text-n-700">
            <input
              type="radio"
              className="mt-1"
              checked={estrategia === "mover"}
              onChange={() => setEstrategia("mover")}
            />
            <span>Mover os alunos para outra série</span>
          </label>

          {estrategia === "mover" && (
            <div className="flex flex-col gap-2 pl-6">
              <Select value={destinoId} onChange={(e) => setDestinoId(e.target.value)}>
                <option value="">Selecione a série destino…</option>
                {outras.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.nome}
                  </option>
                ))}
                <option value="__nova__">+ Criar nova série…</option>
              </Select>
              {criandoSerie && (
                <Input
                  autoFocus
                  value={novaSerie}
                  onChange={(e) => setNovaSerie(e.target.value)}
                  placeholder="Nome da nova série (ex.: 6ª série A)"
                />
              )}
            </div>
          )}

          <label className="flex items-start gap-2 font-semibold text-n-700">
            <input
              type="radio"
              className="mt-1"
              checked={estrategia === "excluir"}
              onChange={() => setEstrategia("excluir")}
            />
            <span>Excluir os {total} aluno(s) junto com a série</span>
          </label>
        </div>
      )}
    </Modal>
  );
}

// --------------------------------------------------------------------------- //
// Alerta de cobertura de contatos: quantos alunos da turma estão sem nenhum
// responsável com WhatsApp vinculado, com disparo de aviso ao professor.
function CoberturaAlerta({
  sala,
  cobertura,
  onMudou,
}: {
  sala: Sala;
  cobertura: CoberturaSala | null;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [notificando, setNotificando] = useState(false);
  const [telefone, setTelefone] = useState("");
  const [mensagem, setMensagem] = useState("");
  const [enviando, setEnviando] = useState(false);

  if (!cobertura || cobertura.total_alunos === 0) return null;

  const semContato = cobertura.total_sem_contato;

  async function notificar() {
    if (!telefone.trim()) {
      toast({ tone: "danger", title: "Informe o WhatsApp do professor." });
      return;
    }
    setEnviando(true);
    try {
      await notificarProfessor(sala.id, telefone.trim(), mensagem.trim());
      setNotificando(false);
      setTelefone("");
      setMensagem("");
      await onMudou();
      toast({ tone: "success", title: "Aviso enviado ao professor." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao notificar." });
    } finally {
      setEnviando(false);
    }
  }

  if (semContato === 0) {
    return (
      <div className="mb-3.5 rounded-[10px] border border-success/30 bg-success-soft px-3.5 py-3 text-[13px] font-semibold text-success">
        ✓ Todos os {cobertura.total_alunos} aluno(s) da turma têm contato de responsável.
      </div>
    );
  }

  return (
    <div className="mb-3.5 rounded-[10px] border border-warning/40 bg-warning-soft px-3.5 py-3 text-[13px]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold text-warning">
          ⚠️ {cobertura.total_alunos} aluno(s) na turma · {semContato} sem contato de responsável
        </p>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setNotificando(true)}
          className="print:hidden"
        >
          Notificar professor
        </Button>
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-warning/90">
        {cobertura.alunos_sem_contato.map((a) => (
          <li key={a.id}>
            • {a.nome}
            {a.matricula ? ` (${a.matricula})` : ""}
          </li>
        ))}
      </ul>

      <Modal
        open={notificando}
        onClose={() => setNotificando(false)}
        title={`Notificar professor — ${sala.nome}`}
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setNotificando(false)}>
              Cancelar
            </Button>
            <Button size="sm" onClick={notificar} loading={enviando}>
              Enviar aviso
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <p className="text-n-600">
            Enviaremos ao professor um aviso pelo WhatsApp com os {semContato} aluno(s) sem contato,
            pedindo que colete os números na reunião.
          </p>
          <Field label="WhatsApp do professor">
            <Input
              autoFocus
              mono
              value={telefone}
              onChange={(e) => setTelefone(e.target.value)}
              placeholder="+5511999990000"
            />
          </Field>
          <Field label="Mensagem (opcional)">
            <Textarea
              rows={3}
              value={mensagem}
              onChange={(e) => setMensagem(e.target.value)}
              placeholder="Ex.: Prezado professor, na reunião de hoje…"
            />
          </Field>
        </div>
      </Modal>
    </div>
  );
}

// --------------------------------------------------------------------------- //
function SalaDetalhe({
  sala,
  pais,
  cobertura,
  onMudou,
}: {
  sala: Sala | null;
  pais: Pai[];
  cobertura: CoberturaSala | null;
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

      <CoberturaAlerta sala={sala} cobertura={cobertura} onMudou={onMudou} />

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
