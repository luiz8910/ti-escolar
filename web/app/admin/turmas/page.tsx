"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  Aluno,
  dadosDaTurma,
  DadosTurma,
  Turno,
  TURNOS,
  turmaVazia,
  atualizarSala,
  CoberturaSala,
  coberturaDasSalas,
  criarSala,
  exigeEscolhaDeEscola,
  getSessao,
  listarAlunos,
  listarSalas,
  logout,
  notificarProfessor,
  Pai,
  relatorioPaisDaSala,
  removerSala,
  Sala,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { GradeHorario } from "@/components/admin/GradeHorario";
import { Badge } from "@/components/ui/Badge";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select, Field, Textarea } from "@/components/ui/form";
import { CampoTelefone } from "@/components/ui/campos";
import { TableWrap, Table, Th, Td, Tr } from "@/components/ui/Table";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { UsersIcon, PlusIcon } from "@/components/ui/icons";
import { formatarTelefone } from "@/lib/mascaras";

export default function SalasEPais() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [salas, setSalas] = useState<Sala[]>([]);
  const [coberturas, setCoberturas] = useState<Record<string, CoberturaSala>>({});
  const [selecionada, setSelecionada] = useState<Sala | null>(null);
  const toast = useToast();

  const recarregar = useCallback(async () => {
    // O cadastro de responsáveis saiu desta tela (apontamento de 10/08): ele vive em
    // Alunos, e a lista da turma é derivada dos alunos ativos.
    const [ss, cobs] = await Promise.all([listarSalas(), coberturaDasSalas()]);
    setSalas(ss);
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
      title="Turmas"
      user={{
        name: usuario.nome,
        role: usuario.papel === "super_admin" ? "Super Admin" : "Admin da escola",
      }}
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
            cobertura={selecionada ? coberturas[selecionada.id] ?? null : null}
            onMudou={recarregar}
          />
        </div>
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
  // `criando` abre o formulário estruturado; `editando` carrega a turma existente nele.
  const [criando, setCriando] = useState(false);
  const [editando, setEditando] = useState<Sala | null>(null);
  const [excluindo, setExcluindo] = useState<Sala | null>(null);

  return (
    <Card className="flex flex-col">
      <CardHeader title="Turmas" count={salas.length} />
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
                <span>
                  {s.nome}
                  {(s.periodo || s.numero_sala) && (
                    <span
                      className={
                        "ml-1.5 text-[11px] font-medium " +
                        (active ? "text-white/70" : "text-n-400")
                      }
                    >
                      {[
                        s.periodo && TURNOS.find((t) => t.valor === s.periodo)?.rotulo,
                        s.numero_sala && `sala ${s.numero_sala}`,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  )}
                </span>
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
                onClick={() => setEditando(s)}
                title="Editar turma"
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

      <div className="mt-auto border-t border-n-100 pt-3.5">
        <Button
          size="sm"
          onClick={() => setCriando(true)}
          leftIcon={<PlusIcon size={15} />}
        >
          Nova turma
        </Button>
      </div>

      {(criando || editando) && (
        <TurmaModal
          sala={editando}
          onFechar={() => {
            setCriando(false);
            setEditando(null);
          }}
          onSalvo={async () => {
            setCriando(false);
            setEditando(null);
            await onMudou();
          }}
        />
      )}

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
  const [destinoId, setDestinoId] = useState("");
  const [novaSerie, setNovaSerie] = useState("");
  const [totalAlunos, setTotalAlunos] = useState(0);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    listarAlunos(sala.id, undefined, 1, 200)
      .then((p) => {
        setAlunos(p.itens);
        // O total vem do servidor: o diálogo precisa saber quantos alunos a série tem,
        // não quantos couberam na página.
        setTotalAlunos(p.meta.total);
      })
      .catch(() => {
        setAlunos([]);
        toast({ tone: "danger", title: "Falha ao verificar alunos da série." });
      });
  }, [sala.id, toast]);

  const total = totalAlunos;
  const outras = salas.filter((s) => s.id !== sala.id);
  const criandoSerie = destinoId === "__nova__";

  async function confirmar() {
    setSalvando(true);
    try {
      if (total === 0) {
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
            A série “{sala.nome}” tem <strong>{total} aluno(s)</strong>. Eles precisam ir
            para outra série — <b>alunos nunca são apagados</b>, porque o registro de que
            estudaram aqui sustenta histórico escolar e declarações. Para tirar um aluno da
            escola, use <b>Desativar</b> na tela de Alunos.
          </p>

          <div className="flex flex-col gap-2">
            <span className="font-semibold text-n-700">Mover os alunos para:</span>
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
            <CampoTelefone autoFocus mono value={telefone} onChange={setTelefone} />
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
  cobertura,
  onMudou,
}: {
  sala: Sala | null;
  cobertura: CoberturaSala | null;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [relatorio, setRelatorio] = useState<Pai[]>([]);

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
          title="Selecione uma turma"
          description="Escolha uma turma para ver os dados, a grade e os responsáveis."
        />
      </Card>
    );
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
      />

      <CoberturaAlerta sala={sala} cobertura={cobertura} onMudou={onMudou} />

      <TableWrap>
        <Table>
          <thead>
            <tr>
              <Th>Responsável</Th>
              <Th>WhatsApp</Th>
            </tr>
          </thead>
          <tbody>
            {relatorio.map((p) => (
              <Tr key={p.id}>
                <Td className="font-medium">
                  {p.nome}
                  {p.tipo_filiacao === "responsavel_legal" && (
                    <span className="ml-1.5 text-[11px] font-semibold text-accent">
                      termo de guarda
                    </span>
                  )}
                </Td>
                <Td className="font-mono text-xs text-n-500">{formatarTelefone(p.telefone)}</Td>
              </Tr>
            ))}
            {relatorio.length === 0 && (
              <Tr>
                <Td colSpan={2} className="text-n-400">
                  Nenhum responsável vinculado a esta sala.
                </Td>
              </Tr>
            )}
          </tbody>
        </Table>
      </TableWrap>

      <p className="mt-3.5 text-[11.5px] text-n-400 print:hidden">
        Esta lista é <b>derivada dos alunos ativos</b> da turma: um responsável está aqui
        porque tem filho matriculado nela. Para incluir ou tirar alguém, mude os
        responsáveis do aluno em <b>Alunos</b>.
      </p>
    </Card>
  );
}

// --------------------------------------------------------------------------- //

// --------------------------------------------------------------------------- //
/**
 * Cadastro da turma: identificação estruturada + grade (nos dois formatos da decisão B).
 *
 * O `nome` deixou de ser digitado — o back-end o deriva de etapa + turma. Texto livre
 * deixava "4ª B", "4ª série B" e "4a serie B" conviverem como turmas diferentes, com
 * alunos espalhados entre elas.
 */
function TurmaModal({
  sala,
  onFechar,
  onSalvo,
}: {
  /** `null` = criando. */
  sala: Sala | null;
  onFechar: () => void;
  onSalvo: () => Promise<void>;
}) {
  const toast = useToast();
  const [dados, setDados] = useState<DadosTurma>(sala ? dadosDaTurma(sala) : turmaVazia());
  const [descricao, setDescricao] = useState(sala?.descricao ?? "");
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  const set = <K extends keyof DadosTurma>(campo: K, valor: DadosTurma[K]) =>
    setDados((atual) => ({ ...atual, [campo]: valor }));

  async function salvar() {
    setSalvando(true);
    setErro("");
    try {
      if (sala) {
        await atualizarSala(sala.id, "", descricao, dados);
      } else {
        await criarSala("", descricao, dados);
      }
      toast({ tone: "success", title: sala ? "Turma atualizada." : "Turma criada." });
      await onSalvo();
    } catch (e) {
      // O back-end recusa turma repetida no mesmo ano e grade inconsistente; mostrar no
      // formulário, e não num toast que some, é o que permite corrigir sem reabrir.
      setErro(e instanceof Error ? e.message : "Falha ao salvar a turma.");
    } finally {
      setSalvando(false);
    }
  }

  const previa = [dados.etapa.trim(), dados.turma.trim().toUpperCase()]
    .filter(Boolean)
    .join(" ");

  return (
    <Modal
      open
      onClose={onFechar}
      title={sala ? `Editar ${sala.nome}` : "Nova turma"}
      className="max-w-2xl"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onFechar}>
            Cancelar
          </Button>
          <Button size="sm" onClick={salvar} disabled={salvando}>
            {salvando ? "Salvando…" : "Salvar turma"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Field label="Ano letivo" htmlFor="t-ano">
            <Input
              id="t-ano"
              type="number"
              value={dados.ano_letivo || ""}
              onChange={(e) => set("ano_letivo", Number(e.target.value))}
            />
          </Field>
          <Field label="Etapa / série" htmlFor="t-etapa">
            <Input
              id="t-etapa"
              value={dados.etapa}
              onChange={(e) => set("etapa", e.target.value)}
              placeholder="4ª série"
            />
          </Field>
          <Field label="Turma" htmlFor="t-turma">
            <Select
              id="t-turma"
              value={dados.turma}
              onChange={(e) => set("turma", e.target.value)}
            >
              <option value="">—</option>
              {["A", "B", "C", "D"].map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Nº da sala" htmlFor="t-sala">
            <Input
              id="t-sala"
              value={dados.numero_sala}
              onChange={(e) => set("numero_sala", e.target.value)}
              placeholder="12"
            />
          </Field>
        </div>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <Field label="Período" htmlFor="t-periodo">
            <Select
              id="t-periodo"
              value={dados.periodo}
              onChange={(e) => set("periodo", e.target.value as Turno | "")}
            >
              <option value="">Não informado</option>
              {TURNOS.map((t) => (
                <option key={t.valor} value={t.valor}>
                  {t.rotulo}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Observações" htmlFor="t-desc">
            <Input
              id="t-desc"
              value={descricao}
              onChange={(e) => setDescricao(e.target.value)}
            />
          </Field>
        </div>

        {previa && (
          <p className="text-[12px] text-n-500">
            A turma vai aparecer como <b>{previa}</b> — o nome é montado a partir da etapa e
            da letra.
          </p>
        )}

        <GradeHorario
          grade={dados.grade_horario}
          onChange={(g) => set("grade_horario", g)}
        />

        {erro && (
          <p className="rounded-lg bg-danger-soft px-3 py-2 text-[12.5px] text-danger">
            {erro}
          </p>
        )}
      </div>
    </Modal>
  );
}
