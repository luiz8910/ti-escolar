"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  abrirSolicitacao,
  CategoriaSolicitacao,
  confirmarLeitura,
  conversaComResponsavel,
  enviarAoResponsavel,
  getSessaoProfessor,
  Interlocutor,
  logoutProfessor,
  MensagemMediada,
  meusInterlocutores,
  meusRecados,
  minhasSolicitacoes,
  ProfessorLogado,
  RecadoDoProfessor,
  SolicitacaoInternaProfessor,
  solicitarImpressaoProfessor,
} from "@/lib/professor";

import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/form";
import { Badge } from "@/components/ui/Badge";
import { useToast } from "@/components/ui/Toast";
import { CheckIcon, PrintIcon } from "@/components/ui/icons";

export default function PortalProfessor() {
  const router = useRouter();
  const toast = useToast();
  const [professor, setProfessor] = useState<ProfessorLogado | null>(null);
  const [recados, setRecados] = useState<RecadoDoProfessor[]>([]);

  const recarregar = useCallback(async () => {
    setRecados(await meusRecados());
  }, []);

  useEffect(() => {
    const s = getSessaoProfessor();
    if (!s) {
      router.replace("/professor/login");
      return;
    }
    setProfessor(s.professor);
    recarregar().catch(() => toast({ tone: "danger", title: "Falha ao carregar recados." }));
  }, [router, recarregar, toast]);

  async function confirmar(id: string) {
    try {
      await confirmarLeitura(id);
      await recarregar();
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao confirmar." });
    }
  }

  if (!professor) return null;

  const pendentes = recados.filter((r) => !r.lido).length;

  return (
    <div className="min-h-screen bg-n-50">
      <header className="flex items-center justify-between border-b border-n-100 bg-white px-4 py-3">
        <div>
          <div className="text-sm font-extrabold tracking-tight text-n-900">
            TI<span className="text-brand-600">·</span>Escolar
          </div>
          <div className="text-xs text-n-500">Mural · {professor.nome}</div>
        </div>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => {
            logoutProfessor();
            router.replace("/professor/login");
          }}
        >
          Sair
        </Button>
      </header>

      <main className="mx-auto flex max-w-2xl flex-col gap-4 p-4">
        <Card>
          <CardHeader
            title="Recados da secretaria"
            action={
              pendentes > 0 ? (
                <Badge tone="warning">{pendentes} não lido(s)</Badge>
              ) : (
                <Badge tone="success" dot>
                  Tudo em dia
                </Badge>
              )
            }
          />
          {recados.length === 0 ? (
            <p className="text-sm text-n-500">Nenhum recado no momento.</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {recados.map((r) => (
                <li
                  key={r.id}
                  className={`rounded-xl border p-3 ${
                    r.lido ? "border-n-100 bg-white" : "border-brand-200 bg-brand-50"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-bold text-n-900">{r.titulo}</div>
                      <div className="mt-0.5 text-xs text-n-400">
                        {r.autor_nome || "Secretaria"} ·{" "}
                        {new Date(r.criado_em).toLocaleString("pt-BR")}
                      </div>
                    </div>
                    {r.lido ? (
                      <Badge tone="success" dot>
                        Lido
                      </Badge>
                    ) : (
                      <Button
                        size="sm"
                        leftIcon={<CheckIcon size={14} />}
                        onClick={() => confirmar(r.id)}
                      >
                        Confirmar leitura
                      </Button>
                    )}
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm text-n-700">{r.corpo}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <SolicitarImpressao />
        <CanalSecretaria />
        <MensagensResponsaveis />
      </main>
    </div>
  );
}

const CATEGORIA_LABEL: Record<CategoriaSolicitacao, string> = {
  secretaria: "Secretaria",
  gestao: "Gestão",
  pedagogico: "Pedagógico",
};

function CanalSecretaria() {
  const toast = useToast();
  const [itens, setItens] = useState<SolicitacaoInternaProfessor[]>([]);
  const [assunto, setAssunto] = useState("");
  const [corpo, setCorpo] = useState("");
  const [categoria, setCategoria] = useState<CategoriaSolicitacao>("secretaria");

  const recarregar = useCallback(async () => {
    setItens(await minhasSolicitacoes());
  }, []);

  useEffect(() => {
    recarregar().catch(() => {});
  }, [recarregar]);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (!assunto.trim() || !corpo.trim()) return;
    try {
      await abrirSolicitacao({ assunto: assunto.trim(), corpo: corpo.trim(), categoria });
      setAssunto("");
      setCorpo("");
      setCategoria("secretaria");
      await recarregar();
      toast({ tone: "success", title: "Solicitação enviada à escola." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao enviar." });
    }
  }

  return (
    <Card>
      <CardHeader title="Falar com a escola" />
      <p className="mb-3 text-xs text-n-400">
        Avisos, faltas e pedidos — registrados no sistema e encaminhados para a área
        certa, sem WhatsApp pessoal.
      </p>
      <form onSubmit={enviar} className="mb-3 flex flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          <Input
            className="flex-1 min-w-[180px]"
            value={assunto}
            onChange={(e) => setAssunto(e.target.value)}
            placeholder="Assunto"
          />
          <Select
            className="w-40"
            value={categoria}
            onChange={(e) => setCategoria(e.target.value as CategoriaSolicitacao)}
          >
            <option value="secretaria">Secretaria</option>
            <option value="gestao">Gestão</option>
            <option value="pedagogico">Pedagógico</option>
          </Select>
        </div>
        <Input
          value={corpo}
          onChange={(e) => setCorpo(e.target.value)}
          placeholder="Escreva sua mensagem"
        />
        <div>
          <Button size="sm" type="submit">
            Enviar à escola
          </Button>
        </div>
      </form>

      {itens.length > 0 && (
        <ul className="flex flex-col gap-2">
          {itens.map((s) => (
            <li key={s.id} className="rounded-xl border border-n-100 p-3">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-n-900">{s.assunto}</span>
                <Badge tone="neutral">{CATEGORIA_LABEL[s.categoria]}</Badge>
                <Badge tone={s.status === "resolvida" ? "success" : "brand"}>
                  {s.status}
                </Badge>
              </div>
              <p className="mt-1 whitespace-pre-wrap text-sm text-n-700">{s.corpo}</p>
              {s.resposta && (
                <div className="mt-2 rounded-lg bg-n-50 p-2 text-sm text-n-700">
                  <span className="text-xs font-bold text-n-500">Resposta:</span>{" "}
                  {s.resposta}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function MensagensResponsaveis() {
  const toast = useToast();
  const [interlocutores, setInterlocutores] = useState<Interlocutor[]>([]);
  const [ativo, setAtivo] = useState<string | null>(null);
  const [thread, setThread] = useState<MensagemMediada[]>([]);
  const [telefone, setTelefone] = useState("");
  const [texto, setTexto] = useState("");

  const recarregar = useCallback(async () => {
    setInterlocutores(await meusInterlocutores());
  }, []);

  useEffect(() => {
    recarregar().catch(() => {});
  }, [recarregar]);

  const abrirThread = useCallback(async (tel: string) => {
    setAtivo(tel);
    setThread(await conversaComResponsavel(tel));
  }, []);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    const destino = (ativo ?? telefone).trim();
    if (!destino || !texto.trim()) return;
    try {
      await enviarAoResponsavel(destino, texto.trim());
      setTexto("");
      await recarregar();
      await abrirThread(destino);
      toast({ tone: "success", title: "Mensagem enviada pelo número da escola." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao enviar." });
    }
  }

  return (
    <Card>
      <CardHeader title="Mensagens dos responsáveis" />
      <p className="mb-3 text-xs text-n-400">
        Converse com os responsáveis pelo sistema — a mensagem sai pelo número da escola,
        sem expor o seu WhatsApp.
      </p>

      {interlocutores.length > 0 && (
        <ul className="mb-3 flex flex-col gap-1.5">
          {interlocutores.map((i) => (
            <li key={i.contato_telefone}>
              <button
                type="button"
                onClick={() => abrirThread(i.contato_telefone)}
                className={`w-full rounded-lg border px-3 py-2 text-left text-sm ${
                  ativo === i.contato_telefone
                    ? "border-brand-200 bg-brand-50"
                    : "border-n-100 bg-white hover:bg-n-50"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-n-900">
                    {i.contato_nome || i.contato_telefone}
                  </span>
                  <span className="text-xs text-n-400">{i.total_mensagens} msg</span>
                </div>
                <div className="truncate text-xs text-n-500">{i.ultima_previa}</div>
              </button>
            </li>
          ))}
        </ul>
      )}

      {ativo && (
        <div className="mb-3 flex flex-col gap-1.5 rounded-lg bg-n-50 p-3">
          {thread.map((m) => (
            <div
              key={m.id}
              className={`max-w-[85%] rounded-lg px-3 py-1.5 text-sm ${
                m.direcao === "professor_para_responsavel"
                  ? "self-end bg-brand-100 text-brand-800"
                  : "self-start bg-white text-n-700"
              }`}
            >
              {m.corpo}
            </div>
          ))}
        </div>
      )}

      <form onSubmit={enviar} className="flex flex-col gap-2">
        {!ativo && (
          <Input
            value={telefone}
            onChange={(e) => setTelefone(e.target.value)}
            placeholder="WhatsApp do responsável, ex.: +5515999990000"
          />
        )}
        <div className="flex gap-2">
          <Input
            className="flex-1"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder={ativo ? `Responder ${ativo}` : "Mensagem"}
          />
          <Button size="sm" type="submit">
            Enviar
          </Button>
        </div>
        {ativo && (
          <button
            type="button"
            onClick={() => {
              setAtivo(null);
              setThread([]);
            }}
            className="self-start text-xs text-n-500 underline"
          >
            Nova conversa
          </button>
        )}
      </form>
    </Card>
  );
}

function SolicitarImpressao() {
  const toast = useToast();
  const [arquivo, setArquivo] = useState("");
  const [copias, setCopias] = useState(1);
  const [colorido, setColorido] = useState(false);
  const [frenteVerso, setFrenteVerso] = useState(false);
  const [observacao, setObservacao] = useState("");

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (!arquivo.trim() || copias < 1) return;
    try {
      await solicitarImpressaoProfessor({
        arquivo_nome: arquivo.trim(),
        copias,
        colorido,
        frente_verso: frenteVerso,
        observacao: observacao.trim(),
      });
      setArquivo("");
      setCopias(1);
      setColorido(false);
      setFrenteVerso(false);
      setObservacao("");
      toast({ tone: "success", title: "Enviado para a fila de impressão da secretaria." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao enviar." });
    }
  }

  return (
    <Card>
      <CardHeader title="Solicitar impressão" />
      <p className="mb-3 text-xs text-n-400">
        Informe o arquivo e os parâmetros. O pedido cai na fila da secretaria.
      </p>
      <form onSubmit={enviar} className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          <Input
            className="flex-1 min-w-[180px]"
            value={arquivo}
            onChange={(e) => setArquivo(e.target.value)}
            placeholder="Nome do arquivo, ex.: prova_5A.pdf"
          />
          <Input
            className="w-24"
            type="number"
            min={1}
            value={copias}
            onChange={(e) => setCopias(Number(e.target.value))}
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
        </div>
        <Input
          value={observacao}
          onChange={(e) => setObservacao(e.target.value)}
          placeholder="Observação (opcional)"
        />
        <div>
          <Button size="sm" type="submit" leftIcon={<PrintIcon size={15} />}>
            Enviar para impressão
          </Button>
        </div>
      </form>
    </Card>
  );
}
