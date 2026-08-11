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
  Aluno,
  baixarDocumento,
  CategoriaDocumento,
  classificarDocumento,
  DocumentoRecebido,
  getSessao,
  listarAlunos,
  listarDocumentos,
  logout,
  StatusDocumento,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/form";
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
};
const STATUS_TONE: Record<StatusDocumento, "warning" | "success" | "neutral"> = {
  recebido: "warning",
  processado: "success",
  descartado: "neutral",
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
  const [alunos, setAlunos] = useState<Aluno[]>([]);
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
    carregar().catch(() =>
      toast({ tone: "danger", title: "Falha ao carregar os documentos." }),
    );
    // A lista de alunos alimenta o vínculo; falhar aqui não impede classificar.
    // Só os ativos: vincular um atestado a um ex-aluno é quase sempre engano.
    listarAlunos(undefined, true, 1, 200)
      .then((p) => setAlunos(p.itens))
      .catch(() => undefined);
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
      tenantName="Escola Demonstração"
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
                alunos={alunos}
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
  alunos,
  onBaixar,
  onAtualizar,
}: {
  doc: DocumentoRecebido;
  alunos: Aluno[];
  onBaixar: () => void;
  onAtualizar: (
    id: string,
    dados: Parameters<typeof classificarDocumento>[1],
    sucesso: string,
  ) => Promise<void>;
}) {
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
        <Button variant="secondary" onClick={onBaixar}>
          Baixar
        </Button>
      </div>

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

        <Select
          className="w-56"
          value={doc.aluno_id ?? ""}
          onChange={(e) =>
            onAtualizar(
              doc.id,
              { aluno_id: e.target.value || null },
              "Aluno vinculado.",
            )
          }
        >
          <option value="">Sem aluno vinculado</option>
          {alunos.map((a) => (
            <option key={a.id} value={a.id}>
              {a.nome}
            </option>
          ))}
        </Select>

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
    </div>
  );
}
