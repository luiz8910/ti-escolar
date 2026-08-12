"use client";

/**
 * Documentos que os responsáveis enviaram pelo WhatsApp (§6k).
 *
 * A tela existe para uma rotina de época de matrícula: chegou um monte de foto, e alguém
 * precisa dizer o que cada uma é, de qual aluno, e marcar o que já foi tratado. Por isso
 * o padrão é mostrar **só os recebidos** — o que ainda exige ação — e não o arquivo todo.
 *
 * O arquivo nunca tem link direto: o download passa pela API autenticada e é auditado.
 * A data de expurgo aparece em cada item, porque prazo de retenção que ninguém vê é
 * prazo que ninguém cumpre.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  baixarDocumento,
  bloquearNumero,
  CategoriaDocumento,
  classificarDocumento,
  DocumentoRecebido,
  exigeEscolhaDeEscola,
  getSessao,
  DocumentoLido,
  lerDocumentoPorIA,
  listarDocumentos,
  previewDocumento,
  logout,
  StatusDocumento,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { BuscaAluno } from "@/components/admin/BuscaAluno";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import {
  Paginacao,
  PaginaMeta,
  salvarTamanhoPreferido,
  tamanhoPreferido,
} from "@/components/ui/Paginacao";

const CATEGORIA_LABEL: Record<CategoriaDocumento, string> = {
  matricula: "Matrícula",
  atestado: "Atestado",
  comprovante: "Comprovante",
  outro: "Outro",
};

const STATUS_LABEL: Record<StatusDocumento, string> = {
  recebido: "A conferir",
  processado: "Processado",
  descartado: "Descartado",
  quarentena: "Origem desconhecida",
};
const STATUS_TONE: Record<StatusDocumento, "warning" | "success" | "neutral" | "danger"> = {
  recebido: "warning",
  processado: "success",
  descartado: "neutral",
  quarentena: "danger",
};

function data(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export default function DocumentosRecebidos() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [itens, setItens] = useState<DocumentoRecebido[]>([]);
  const [categoria, setCategoria] = useState("");
  // Padrão "a conferir": a tela é uma fila de trabalho, não um arquivo morto.
  const [status, setStatus] = useState<string>("recebido");
  const [meta, setMeta] = useState<PaginaMeta>({
    pagina: 1,
    por_pagina: 25,
    total: 0,
    total_paginas: 1,
  });
  const toast = useToast();

  const carregar = useCallback(
    async (pagina = 1, porPagina?: number) => {
      const dados = await listarDocumentos({
        categoria: categoria || undefined,
        status: status || undefined,
        pagina,
        porPagina: porPagina ?? tamanhoPreferido("documentos", 25),
      });
      setItens(dados.itens);
      setMeta(dados.meta);
    },
    [categoria, status],
  );

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
    carregar().catch(() =>
      toast({ tone: "danger", title: "Falha ao carregar os documentos." }),
    );
  }, [router, carregar, toast]);

  async function atualizar(
    id: string,
    dados: Parameters<typeof classificarDocumento>[1],
    sucesso: string,
  ) {
    try {
      await classificarDocumento(id, dados);
      await carregar(meta.pagina);
      toast({ tone: "success", title: sucesso });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha." });
    }
  }

  async function abrir(doc: DocumentoRecebido) {
    try {
      const { url, nome } = await baixarDocumento(doc.id);
      const link = document.createElement("a");
      link.href = url;
      link.download = nome;
      link.click();
      // Sem revoke, os bytes do atestado ficam pendurados na memória da aba.
      URL.revokeObjectURL(url);
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha." });
    }
  }

  if (!usuario) return null;

  return (
    <AppShell
      title="Documentos recebidos"
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
          title={`Documentos (${meta.total})`}
          action={
            <div className="flex flex-wrap gap-2">
              <Select
                className="w-40"
                value={categoria}
                onChange={(e) => setCategoria(e.target.value)}
              >
                <option value="">Todas as finalidades</option>
                {Object.entries(CATEGORIA_LABEL).map(([v, r]) => (
                  <option key={v} value={v}>
                    {r}
                  </option>
                ))}
              </Select>
              <Select
                className="w-40"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                <option value="recebido">A conferir</option>
                <option value="quarentena">Origem desconhecida</option>
                <option value="processado">Processados</option>
                <option value="descartado">Descartados</option>
                <option value="">Todos</option>
              </Select>
            </div>
          }
        />
        <p className="mb-3 text-sm text-n-500">
          Arquivos que os responsáveis enviaram pelo WhatsApp — atestado, documento de
          matrícula, comprovante. Ficam guardados na escola, e não no celular de quem
          atendeu.
        </p>

        {itens.length === 0 ? (
          <EmptyState
            title="Nenhum documento no filtro atual"
            description="Quando um responsável enviar uma foto ou um PDF pelo WhatsApp da escola, ele aparece aqui."
          />
        ) : (
          <div className="flex flex-col gap-3">
            {itens.map((d) => (
              <ItemDocumento
                key={d.id}
                doc={d}
                onBaixar={() => abrir(d)}
                onAtualizar={atualizar}
              />
            ))}
          </div>
        )}

        <Paginacao
          meta={meta}
          rotulo="documento(s)"
          onPagina={(p) => carregar(p)}
          onTamanho={(t) => {
            salvarTamanhoPreferido("documentos", t);
            carregar(1, t);
          }}
        />
      </Card>
    </AppShell>
  );
}

function ItemDocumento({
  doc,
  onBaixar,
  onAtualizar,
}: {
  doc: DocumentoRecebido;
  onBaixar: () => void;
  onAtualizar: (
    id: string,
    dados: Parameters<typeof classificarDocumento>[1],
    sucesso: string,
  ) => Promise<void>;
}) {
  const toast = useToast();
  const [preview, setPreview] = useState(false);
  const [bloqueando, setBloqueando] = useState(false);
  const [lendo, setLendo] = useState(false);
  const [lido, setLido] = useState<DocumentoLido | null>(null);

  async function lerPorIA() {
    setLendo(true);
    try {
      const resultado = await lerDocumentoPorIA(doc.id);
      setLido(resultado);
      if (resultado.erro) toast({ tone: "info", title: resultado.erro });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha." });
    } finally {
      setLendo(false);
    }
  }

  return (
    <div className="rounded-xl border border-n-200 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-n-900">
              {doc.nome_arquivo || (doc.eh_imagem ? "Foto enviada" : "Arquivo")}
            </span>
            <Badge tone={STATUS_TONE[doc.status]}>{STATUS_LABEL[doc.status]}</Badge>
            {doc.categoria_sugerida && doc.status === "recebido" && (
              <Badge tone="neutral">
                sugerido: {CATEGORIA_LABEL[doc.categoria_sugerida]}
              </Badge>
            )}
          </div>
          {doc.observacao && (
            <p className="mt-1.5 text-sm text-n-600">“{doc.observacao}”</p>
          )}
          <p className="mt-1 text-[12px] text-n-400">
            {doc.contato_nome || doc.contato} · {doc.tamanho_legivel} · recebido em{" "}
            {data(doc.criado_em)}
            {doc.aluno_nome && ` · aluno: ${doc.aluno_nome}`}
            {doc.expira_em && ` · apagado em ${data(doc.expira_em)}`}
          </p>
        </div>
        <div className="flex flex-none gap-2">
          <Button variant="secondary" onClick={() => setPreview(true)}>
            Ver
          </Button>
          <Button variant="ghost" onClick={onBaixar}>
            Baixar
          </Button>
        </div>
      </div>

      {doc.status === "quarentena" && (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-[12.5px] text-danger">
          <span className="flex-1">
            Enviado por um número <b>sem cadastro</b> na escola. Pode ser um responsável
            que trocou de telefone — confira antes de descartar.
          </span>
          <button
            type="button"
            onClick={() =>
              onAtualizar(doc.id, { status: "recebido" }, "Documento liberado para a fila.")
            }
            className="font-semibold underline"
          >
            Liberar para a fila
          </button>
          <button
            type="button"
            onClick={() => setBloqueando(true)}
            className="font-semibold underline"
          >
            Bloquear envio deste número
          </button>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-n-100 pt-3">
        <Select
          className="w-44"
          value={doc.categoria}
          onChange={(e) =>
            onAtualizar(
              doc.id,
              { categoria: e.target.value as CategoriaDocumento },
              "Finalidade atualizada.",
            )
          }
        >
          {Object.entries(CATEGORIA_LABEL).map(([v, r]) => (
            <option key={v} value={v}>
              {r}
            </option>
          ))}
        </Select>

        <BuscaAluno
          alunoId={doc.aluno_id}
          alunoNome={doc.aluno_nome}
          onSelecionar={(id) =>
            onAtualizar(
              doc.id,
              { aluno_id: id },
              id ? "Aluno vinculado." : "Aluno desvinculado.",
            )
          }
        />

        <Button variant="ghost" onClick={lerPorIA} disabled={lendo}>
          {lendo ? "Lendo…" : "Ler documento"}
        </Button>

        <div className="ml-auto flex gap-2">
          {doc.status !== "processado" && (
            <Button
              onClick={() =>
                onAtualizar(doc.id, { status: "processado" }, "Marcado como processado.")
              }
            >
              Marcar processado
            </Button>
          )}
          {doc.status !== "descartado" && (
            <Button
              variant="ghost"
              onClick={() =>
                onAtualizar(doc.id, { status: "descartado" }, "Documento descartado.")
              }
            >
              Descartar
            </Button>
          )}
        </div>
      </div>

      {lido && !lido.erro && (
        <SugestaoDaIA
          lido={lido}
          onAplicar={() => {
            if (lido.categoria) {
              onAtualizar(
                doc.id,
                { categoria: lido.categoria as CategoriaDocumento },
                "Finalidade aplicada.",
              );
            }
            setLido(null);
          }}
          onDescartar={() => setLido(null)}
        />
      )}

      {preview && <PreviewDocumento doc={doc} onFechar={() => setPreview(false)} />}
      {bloqueando && (
        <BloquearNumeroModal
          telefone={doc.contato}
          onFechar={() => setBloqueando(false)}
          onBloqueado={() => {
            setBloqueando(false);
            toast({
              tone: "success",
              title: "Número bloqueado para envio de arquivos.",
              description: "Ele continua sendo atendido normalmente por mensagem de texto.",
            });
          }}
        />
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
/**
 * O que a IA leu — **sugestão**, nunca gravação.
 *
 * Mesmo fluxo da importação em massa (§6c-quater) e da leitura de ficha (§D3): o modelo
 * sugere, o código valida, a secretaria confirma. Aplicar é um clique explícito.
 */
function SugestaoDaIA({
  lido,
  onAplicar,
  onDescartar,
}: {
  lido: DocumentoLido;
  onAplicar: () => void;
  onDescartar: () => void;
}) {
  const temFicha = Object.keys(lido.campos_ficha).length > 0;
  return (
    <div className="mt-3 flex flex-col gap-2 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2.5 text-[12.5px] text-brand-900">
      <p className="font-bold">Leitura por IA — confira antes de aplicar</p>
      {lido.resumo && <p>{lido.resumo}</p>}
      <p>
        {lido.categoria ? (
          <>
            Finalidade sugerida: <b>{CATEGORIA_LABEL[lido.categoria]}</b>
          </>
        ) : (
          "Não foi possível identificar a finalidade."
        )}
        {lido.aluno_nome && (
          <>
            {" · "}aluno mencionado: <b>{lido.aluno_nome}</b>
          </>
        )}
      </p>
      {temFicha && (
        <p className="text-[11.5px]">
          Também foram lidos {Object.keys(lido.campos_ficha).length} campo(s) de ficha de
          matrícula. Abra a ficha do aluno em <b>Alunos</b> para revisá-los — a ficha não é
          preenchida a partir daqui, para nada entrar sem alguém olhar.
        </p>
      )}
      <div className="flex gap-2">
        {lido.categoria && (
          <Button size="sm" onClick={onAplicar}>
            Aplicar finalidade
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={onDescartar}>
          Ignorar
        </Button>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
/**
 * Preview do arquivo — o apontamento pedia "ver, não apenas baixar".
 *
 * O endpoint é autenticado, então a imagem entra por um **blob URL**, revogado ao fechar:
 * nunca um `src` direto com token na URL. Visualizar é acessar o dado, e o acesso é
 * auditado como `documento.visualizar`.
 */
function PreviewDocumento({
  doc,
  onFechar,
}: {
  doc: DocumentoRecebido;
  onFechar: () => void;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    let atual: string | null = null;
    previewDocumento(doc.id)
      .then((u) => {
        atual = u;
        setUrl(u);
        if (!u) setErro(true);
      })
      .catch(() => setErro(true));
    return () => {
      // Sem revoke, os bytes do atestado ficam pendurados na memória da aba.
      if (atual) URL.revokeObjectURL(atual);
    };
  }, [doc.id]);

  return (
    <Modal
      open
      onClose={onFechar}
      title={doc.nome_arquivo || "Documento"}
      className="max-w-3xl"
    >
      {erro && <p className="py-6 text-center text-sm text-n-400">Arquivo indisponível.</p>}
      {!erro && !url && (
        <p className="py-6 text-center text-sm text-n-400">Carregando…</p>
      )}
      {url &&
        (doc.eh_imagem ? (
          // eslint-disable-next-line @next/next/no-img-element -- blob URL de endpoint
          // autenticado: o <Image> do Next tentaria otimizar uma URL local desta aba.
          <img
            src={url}
            alt={doc.nome_arquivo || "Documento recebido"}
            className="mx-auto max-h-[70vh] w-auto rounded-lg"
          />
        ) : (
          <embed src={url} type={doc.mime} className="h-[70vh] w-full rounded-lg" />
        ))}
      <p className="mt-3 text-[11.5px] text-n-400">
        Este acesso fica registrado na auditoria da escola.
      </p>
    </Modal>
  );
}

// --------------------------------------------------------------------------- //
/**
 * Bloqueio de envio de arquivos — **decisão humana**, sempre.
 *
 * Bloqueia a mídia, não a pessoa: o número segue sendo atendido por texto. Silenciar
 * alguém por completo com base num contador é o erro que o produto existe para evitar.
 */
function BloquearNumeroModal({
  telefone,
  onFechar,
  onBloqueado,
}: {
  telefone: string;
  onFechar: () => void;
  onBloqueado: () => void;
}) {
  const toast = useToast();
  const [motivo, setMotivo] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function bloquear() {
    setSalvando(true);
    try {
      await bloquearNumero(telefone, motivo.trim());
      onBloqueado();
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha." });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      open
      onClose={onFechar}
      title={`Bloquear arquivos de ${telefone}`}
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onFechar}>
            Cancelar
          </Button>
          <Button size="sm" onClick={bloquear} disabled={salvando}>
            {salvando ? "Bloqueando…" : "Bloquear envio de arquivos"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="rounded-lg border border-accent/30 bg-accent-soft px-3 py-2 text-[12.5px] text-[#7a5208]">
          O número <b>continua sendo atendido</b> normalmente por mensagem de texto — só o
          envio de arquivos é recusado, com aviso ao remetente. Dá para liberar depois.
        </p>
        <Field label="Motivo (fica na auditoria)">
          <Input
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Ex.: propaganda enviada repetidamente"
          />
        </Field>
      </div>
    </Modal>
  );
}
