"use client";

/**
 * Responsáveis — o CRUD que a API já tinha e o painel não mostrava.
 *
 * Até aqui um responsável só nascia de dentro da tela de Alunos (no vínculo) ou da
 * importação em massa, e não havia onde corrigir o telefone de quem trocou de número —
 * justamente o dado que decide se o aviso chega. Esta tela lista todos, com os alunos de
 * cada um, e edita no painel lateral, no mesmo desenho da tela de Escolas.
 *
 * Os alunos de cada responsável são **derivados da lista de alunos** (que já traz os
 * responsáveis de cada um): a API de responsáveis não devolve o vínculo, e uma chamada por
 * linha seria N+1 só para exibir a tabela.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Aluno,
  atualizarPai,
  cadastrarPai,
  DADOS_RESPONSAVEL_VAZIO,
  DadosResponsavel,
  dadosDoResponsavel,
  desvincularResponsavelDoAluno,
  exigeEscolhaDeEscola,
  getSessao,
  listarAlunos,
  listarTodosOsPais,
  logout,
  Pai,
  removerPai,
  Usuario,
  vincularResponsavelAoAluno,
} from "@/lib/admin";
import { formatarTelefone, telefoneCompleto } from "@/lib/mascaras";

import { AppShell } from "@/components/layout/AppShell";
import { BuscaAluno } from "@/components/admin/BuscaAluno";
import { CamposResponsavel } from "@/components/admin/CamposResponsavel";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { CampoTelefone } from "@/components/ui/campos";
import { cn } from "@/components/ui/cn";
import { Drawer } from "@/components/ui/Drawer";
import { Field, Input } from "@/components/ui/form";
import { CloseIcon, PencilIcon, PlusIcon, SearchIcon, TrashIcon } from "@/components/ui/icons";
import { ConfirmDialog } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";

type Filtro = "todos" | "ativos" | "sem_aluno" | "inativos";

/** Aluno reduzido ao que a linha do responsável exibe. */
interface AlunoVinculado {
  id: string;
  nome: string;
  sala_nome: string;
  ativo: boolean;
}

type Painel = { modo: "novo" } | { modo: "editar"; pai: Pai };

const POR_PAGINA_ALUNOS = 200;

async function listarTodosOsAlunos(): Promise<Aluno[]> {
  const primeira = await listarAlunos(undefined, undefined, 1, POR_PAGINA_ALUNOS);
  const todos = [...primeira.itens];
  for (let p = 2; p <= primeira.meta.total_paginas; p++) {
    todos.push(...(await listarAlunos(undefined, undefined, p, POR_PAGINA_ALUNOS)).itens);
  }
  return todos;
}

function semAcento(texto: string): string {
  return texto.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

function sigla(nome: string): string {
  // Só palavras que começam por letra: "Joana Ribeiro (avó)" vira "JR", não "J(".
  const partes = nome.trim().split(/\s+/).filter((p) => /^\p{L}/u.test(p));
  return ((partes[0]?.[0] ?? "") + (partes.length > 1 ? partes[partes.length - 1][0] : "")).toUpperCase();
}

export default function ResponsaveisPage() {
  const router = useRouter();
  const toast = useToast();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [pais, setPais] = useState<Pai[]>([]);
  const [alunos, setAlunos] = useState<Aluno[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [filtro, setFiltro] = useState<Filtro>("ativos");
  const [busca, setBusca] = useState("");
  const [painel, setPainel] = useState<Painel | null>(null);
  const [excluir, setExcluir] = useState<Pai | null>(null);

  const recarregar = useCallback(async () => {
    const [ps, as] = await Promise.all([listarTodosOsPais(), listarTodosOsAlunos()]);
    setPais(ps.sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR")));
    setAlunos(as);
    setCarregando(false);
  }, []);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    // Super admin sem escola escolhida: a AppShell pede a escolha e nada é buscado.
    if (exigeEscolhaDeEscola()) return;
    recarregar().catch(() => toast({ tone: "danger", title: "Falha ao carregar os responsáveis." }));
  }, [router, recarregar, toast]);

  const alunosPorResponsavel = useMemo(() => {
    const mapa = new Map<string, AlunoVinculado[]>();
    for (const a of alunos) {
      for (const r of a.responsaveis) {
        const lista = mapa.get(r.id) ?? [];
        lista.push({ id: a.id, nome: a.nome, sala_nome: a.sala_nome, ativo: a.ativo });
        mapa.set(r.id, lista);
      }
    }
    return mapa;
  }, [alunos]);

  const contagem = useMemo(
    () => ({
      todos: pais.length,
      ativos: pais.filter((p) => p.ativo).length,
      sem_aluno: pais.filter((p) => !alunosPorResponsavel.has(p.id)).length,
      inativos: pais.filter((p) => !p.ativo).length,
    }),
    [pais, alunosPorResponsavel],
  );

  const visiveis = useMemo(() => {
    const termo = semAcento(busca.trim());
    const digitos = busca.replace(/\D/g, "");
    return pais.filter((p) => {
      if (filtro === "ativos" && !p.ativo) return false;
      if (filtro === "inativos" && p.ativo) return false;
      if (filtro === "sem_aluno" && alunosPorResponsavel.has(p.id)) return false;
      if (!termo) return true;
      const alunosDele = alunosPorResponsavel.get(p.id) ?? [];
      return (
        semAcento(p.nome).includes(termo) ||
        semAcento(p.email).includes(termo) ||
        alunosDele.some((a) => semAcento(a.nome).includes(termo)) ||
        (digitos.length >= 3 && (p.telefone.includes(digitos) || p.cpf.includes(digitos)))
      );
    });
  }, [pais, filtro, busca, alunosPorResponsavel]);

  async function confirmarExclusao() {
    const alvo = excluir;
    setExcluir(null);
    if (!alvo) return;
    try {
      await removerPai(alvo.id);
      await recarregar();
      toast({ tone: "success", title: "Responsável excluído." });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao excluir o responsável.",
      });
    }
  }

  function sair() {
    logout();
    router.replace("/admin/login");
  }

  if (!usuario) return null;

  const filtros: { valor: Filtro; rotulo: string }[] = [
    { valor: "ativos", rotulo: "Ativos" },
    { valor: "sem_aluno", rotulo: "Sem aluno vinculado" },
    { valor: "inativos", rotulo: "Inativos" },
    { valor: "todos", rotulo: "Todos" },
  ];

  const vinculadosExcluir = excluir ? (alunosPorResponsavel.get(excluir.id)?.length ?? 0) : 0;

  return (
    <AppShell
      title="Responsáveis"
      user={{
        name: usuario.nome,
        role: usuario.papel === "super_admin" ? "Super Admin" : "Admin da escola",
      }}
      isSuperAdmin={usuario.papel === "super_admin"}
      onLogout={sair}
    >
      <div className="flex flex-col gap-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h1 className="text-[26px] font-bold tracking-[-0.02em] text-n-900">Responsáveis</h1>
            <p className="hidden text-sm text-n-500 sm:block">
              Pais, mães e responsáveis legais que recebem os avisos da escola pelo WhatsApp.
            </p>
          </div>
          <Button leftIcon={<PlusIcon size={16} />} onClick={() => setPainel({ modo: "novo" })}>
            Novo responsável
          </Button>
        </div>

        <section className="rounded-[14px] border border-n-200 bg-white">
          <div className="flex flex-col-reverse gap-3 border-b border-n-100 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div
              role="tablist"
              aria-label="Filtrar responsáveis"
              className="flex w-fit max-w-full gap-1 overflow-x-auto rounded-[10px] bg-n-100 p-1"
            >
              {filtros.map((f) => {
                const ativo = filtro === f.valor;
                const destaque = f.valor === "sem_aluno" && contagem.sem_aluno > 0;
                return (
                  <button
                    key={f.valor}
                    type="button"
                    role="tab"
                    aria-selected={ativo}
                    onClick={() => setFiltro(f.valor)}
                    className={cn(
                      "flex h-8 flex-none items-center gap-2 rounded-[7px] px-3 text-[13px] transition-colors",
                      ativo
                        ? "bg-white font-semibold text-n-900 shadow-sm"
                        : "font-medium text-n-700 hover:text-n-900",
                    )}
                  >
                    {f.rotulo}
                    <span
                      className={cn(
                        "tabular-nums",
                        destaque
                          ? "rounded-full bg-accent-soft px-[7px] py-px text-[11px] font-bold text-[#8A4B00]"
                          : "text-xs font-medium text-n-500",
                      )}
                    >
                      {contagem[f.valor]}
                    </span>
                  </button>
                );
              })}
            </div>
            <label className="relative flex w-full items-center lg:w-[360px]">
              <SearchIcon size={16} className="pointer-events-none absolute left-3 text-n-500" />
              <input
                type="search"
                aria-label="Buscar responsáveis"
                placeholder="Buscar por nome, telefone, CPF ou aluno"
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                className="h-[38px] w-full rounded-[10px] border border-n-300 bg-white pl-9 pr-3 text-sm text-n-900 outline-none placeholder:text-n-400 focus:border-brand-500 focus:ring-[3px] focus:ring-brand-500/20"
              />
            </label>
          </div>

          {carregando ? (
            <p className="px-5 py-10 text-center text-sm text-n-400">Carregando…</p>
          ) : pais.length === 0 ? (
            <div className="flex flex-col items-center gap-3 px-5 py-12 text-center">
              <p className="text-sm text-n-500">Nenhum responsável cadastrado ainda.</p>
              <Button size="sm" leftIcon={<PlusIcon size={15} />} onClick={() => setPainel({ modo: "novo" })}>
                Cadastrar o primeiro
              </Button>
            </div>
          ) : visiveis.length === 0 ? (
            <p className="px-5 py-10 text-center text-sm text-n-500">
              Nenhum responsável encontrado
              {busca.trim() ? <> para &ldquo;{busca.trim()}&rdquo;</> : " neste filtro"}.
            </p>
          ) : (
            <ul className="divide-y divide-n-100">
              {visiveis.map((p) => (
                <LinhaResponsavel
                  key={p.id}
                  pai={p}
                  alunos={alunosPorResponsavel.get(p.id) ?? []}
                  onEditar={() => setPainel({ modo: "editar", pai: p })}
                  onExcluir={() => setExcluir(p)}
                />
              ))}
            </ul>
          )}
        </section>
      </div>

      {painel && (
        <ResponsavelDrawer
          key={painel.modo === "editar" ? painel.pai.id : "novo"}
          pai={painel.modo === "editar" ? painel.pai : null}
          alunos={painel.modo === "editar" ? (alunosPorResponsavel.get(painel.pai.id) ?? []) : []}
          onClose={() => setPainel(null)}
          onMudou={recarregar}
          onCriado={(pai) => setPainel({ modo: "editar", pai })}
        />
      )}

      <ConfirmDialog
        open={excluir !== null}
        onClose={() => setExcluir(null)}
        onConfirm={confirmarExclusao}
        title="Excluir responsável"
        message={
          `Excluir "${excluir?.nome ?? ""}"? ` +
          (vinculadosExcluir > 0
            ? `Ele deixa de ser responsável por ${vinculadosExcluir} aluno(s) e para de receber os avisos da escola. `
            : "Ele para de receber os avisos da escola. ") +
          "O histórico de conversas continua registrado."
        }
      />
    </AppShell>
  );
}

// --------------------------------------------------------------------------- //
function LinhaResponsavel({
  pai,
  alunos,
  onEditar,
  onExcluir,
}: {
  pai: Pai;
  alunos: AlunoVinculado[];
  onEditar: () => void;
  onExcluir: () => void;
}) {
  return (
    <li
      className={cn(
        "grid grid-cols-1 gap-3 px-5 py-4 lg:grid-cols-[minmax(220px,1.3fr)_170px_minmax(200px,1.4fr)_110px_auto] lg:items-center",
        !pai.ativo && "bg-n-50/60",
      )}
    >
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-10 w-10 flex-none items-center justify-center rounded-full bg-brand-50 text-[13px] font-bold text-brand-700">
          {sigla(pai.nome)}
        </div>
        <div className="min-w-0">
          <div className="truncate text-[14px] font-semibold text-n-900">{pai.nome}</div>
          <div className="truncate text-xs text-n-500">
            {[pai.tipo_filiacao_rotulo, pai.email].filter(Boolean).join(" · ") || "Filiação não informada"}
          </div>
        </div>
      </div>

      <div className="whitespace-nowrap text-[13px] tabular-nums text-n-900">
        {pai.telefone ? formatarTelefone(pai.telefone) : <span className="text-danger">Sem WhatsApp</span>}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {alunos.length === 0 ? (
          <span className="text-[13px] text-n-400">Nenhum aluno vinculado</span>
        ) : (
          alunos.map((a) => (
            <span
              key={a.id}
              title={a.sala_nome}
              className={cn(
                "rounded-full border px-2.5 py-0.5 text-xs",
                a.ativo ? "border-n-200 bg-white text-n-700" : "border-n-200 bg-n-100 text-n-500 line-through",
              )}
            >
              {a.nome}
              {a.sala_nome && <span className="text-n-400"> · {a.sala_nome}</span>}
            </span>
          ))
        )}
      </div>

      <div>
        {pai.ativo ? (
          <Badge tone="success" dot>
            Ativo
          </Badge>
        ) : (
          <Badge>Inativo</Badge>
        )}
      </div>

      <div className="flex justify-start gap-1.5 lg:justify-end">
        <Button size="sm" variant="secondary" leftIcon={<PencilIcon size={14} />} onClick={onEditar}>
          Editar
        </Button>
        <button
          type="button"
          onClick={onExcluir}
          aria-label={`Excluir ${pai.nome}`}
          className="flex h-[34px] w-[34px] items-center justify-center rounded-md text-n-500 hover:bg-danger-soft hover:text-danger"
        >
          <TrashIcon size={16} />
        </button>
      </div>
    </li>
  );
}

// --------------------------------------------------------------------------- //
function ResponsavelDrawer({
  pai,
  alunos,
  onClose,
  onMudou,
  onCriado,
}: {
  pai: Pai | null;
  alunos: AlunoVinculado[];
  onClose: () => void;
  onMudou: () => Promise<void>;
  /** Depois de criar, o painel vira edição — é lá que se vincula o aluno. */
  onCriado: (pai: Pai) => void;
}) {
  const toast = useToast();
  const [nome, setNome] = useState(pai?.nome ?? "");
  const [telefone, setTelefone] = useState(pai?.telefone ?? "");
  const [dados, setDados] = useState<DadosResponsavel>(pai ? dadosDoResponsavel(pai) : DADOS_RESPONSAVEL_VAZIO);
  const [salvando, setSalvando] = useState(false);
  const [vinculando, setVinculando] = useState(false);

  async function salvar(e?: React.FormEvent) {
    e?.preventDefault();
    if (!nome.trim() || !telefone.trim()) {
      toast({ tone: "danger", title: "Nome e WhatsApp são obrigatórios." });
      return;
    }
    if (!telefoneCompleto(telefone)) {
      toast({ tone: "danger", title: "WhatsApp incompleto — informe DDD e número." });
      return;
    }
    setSalvando(true);
    try {
      if (pai) {
        await atualizarPai(pai.id, nome.trim(), telefone.trim(), dados);
        await onMudou();
        toast({ tone: "success", title: "Responsável atualizado." });
        onClose();
      } else {
        const criado = await cadastrarPai(nome.trim(), telefone.trim(), [], dados);
        await onMudou();
        toast({ tone: "success", title: "Responsável cadastrado. Vincule agora os alunos dele." });
        onCriado(criado);
      }
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao salvar o responsável.",
      });
    } finally {
      setSalvando(false);
    }
  }

  async function vincular(alunoId: string | null) {
    if (!pai || !alunoId) return;
    if (alunos.some((a) => a.id === alunoId)) {
      toast({ tone: "info", title: "Este aluno já está vinculado." });
      return;
    }
    setVinculando(true);
    try {
      await vincularResponsavelAoAluno(alunoId, pai.id);
      await onMudou();
      toast({ tone: "success", title: "Aluno vinculado." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao vincular." });
    } finally {
      setVinculando(false);
    }
  }

  async function desvincular(aluno: AlunoVinculado) {
    if (!pai) return;
    try {
      await desvincularResponsavelDoAluno(aluno.id, pai.id);
      await onMudou();
      toast({ tone: "success", title: `Desvinculado de ${aluno.nome}.` });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao desvincular." });
    }
  }

  return (
    <Drawer
      open
      onClose={onClose}
      title={pai ? "Editar responsável" : "Novo responsável"}
      description={
        pai
          ? "Alterar o WhatsApp muda para onde vão os avisos e quem o assistente reconhece."
          : "Só nome e WhatsApp são obrigatórios; o resto pode ser completado depois."
      }
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {pai ? "Fechar" : "Cancelar"}
          </Button>
          <Button loading={salvando} onClick={() => salvar()}>
            {pai ? "Salvar alterações" : "Cadastrar"}
          </Button>
        </>
      }
    >
      <form onSubmit={salvar} className="flex flex-col gap-6">
        <section className="flex flex-col gap-3">
          <h3 className="text-[13px] font-bold uppercase tracking-[0.04em] text-n-500">Identificação</h3>
          <Field label="Nome completo" htmlFor="resp-nome">
            <Input
              id="resp-nome"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex.: Maria da Silva"
              autoFocus
            />
          </Field>
          <Field
            label="WhatsApp"
            htmlFor="resp-telefone"
            hint="O número que recebe os avisos e conversa com o assistente."
          >
            <CampoTelefone id="resp-telefone" value={telefone} onChange={setTelefone} />
          </Field>
        </section>

        <section className="flex flex-col gap-3">
          <h3 className="text-[13px] font-bold uppercase tracking-[0.04em] text-n-500">Cadastro e contato</h3>
          <CamposResponsavel dados={dados} onChange={setDados} idPrefixo="drawer-resp" />
        </section>

        {/* Enter no formulário salva; o botão fica no rodapé fixo do painel. */}
        <button type="submit" className="hidden" aria-hidden tabIndex={-1} />
      </form>

      {pai && (
        <section className="mt-6 flex flex-col gap-3 border-t border-n-100 pt-6">
          <h3 className="text-[13px] font-bold uppercase tracking-[0.04em] text-n-500">
            Alunos vinculados · {alunos.length}
          </h3>
          {alunos.length === 0 ? (
            <p className="text-[13px] text-n-500">
              Nenhum aluno ainda. Sem vínculo, este responsável não entra na cobertura da turma.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {alunos.map((a) => (
                <li
                  key={a.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-n-200 px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="truncate text-[13.5px] font-semibold text-n-900">{a.nome}</div>
                    <div className="text-xs text-n-500">
                      {a.sala_nome || "Sem turma"}
                      {!a.ativo && " · ex-aluno"}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => desvincular(a)}
                    aria-label={`Desvincular ${a.nome}`}
                    className="flex h-8 w-8 flex-none items-center justify-center rounded-md text-n-500 hover:bg-danger-soft hover:text-danger"
                  >
                    <CloseIcon size={15} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className={cn(vinculando && "pointer-events-none opacity-60")}>
            <BuscaAluno
              alunoId={null}
              alunoNome=""
              onSelecionar={(id) => vincular(id)}
              placeholder="Vincular aluno: buscar por nome ou matrícula…"
            />
          </div>
        </section>
      )}
    </Drawer>
  );
}
