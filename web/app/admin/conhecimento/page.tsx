"use client";

/**
 * Base de conhecimento da escola (RAG por tenant).
 *
 * Duas mudanças vindas do teste de 10/08:
 *
 * - **o documento pode ser lido e corrigido.** Antes só dava para enviar e apagar: o texto
 *   original não ficava em lugar nenhum, então mudar uma linha de um procedimento exigia
 *   reenviar tudo do zero;
 * - **apagar virou coisa de super admin.** O que a escola precisa no dia a dia é tirar do
 *   ar um procedimento vencido, e para isso existe "Tirar do ar" — que remove os trechos
 *   do RAG sem destruir o texto. Reversível num clique.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  adicionarConhecimento,
  atualizarConhecimento,
  definirAtivoConhecimento,
  FonteConhecimento,
  exigeEscolhaDeEscola,
  getSessao,
  listarConhecimento,
  logout,
  obterConhecimento,
  removerConhecimento,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select, Textarea, Field } from "@/components/ui/form";
import { Badge } from "@/components/ui/Badge";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { BookIcon, FileIcon } from "@/components/ui/icons";

const TIPOS = [
  { valor: "procedimento", rotulo: "Procedimento" },
  { valor: "aviso", rotulo: "Aviso" },
  { valor: "faq", rotulo: "FAQ" },
];

export default function BaseDeConhecimento() {
  const router = useRouter();
  const toast = useToast();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [fontes, setFontes] = useState<FonteConhecimento[]>([]);

  const recarregar = useCallback(async () => {
    setFontes(await listarConhecimento());
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
    recarregar().catch(() => toast({ tone: "danger", title: "Falha ao carregar documentos." }));
  }, [router, recarregar, toast]);

  function sair() {
    logout();
    router.replace("/admin/login");
  }

  if (!usuario) return null;

  return (
    <AppShell
      title="Base de conhecimento"
      user={{
        name: usuario.nome,
        role: usuario.papel === "super_admin" ? "Super Admin" : "Admin da escola",
      }}
      isSuperAdmin={usuario.papel === "super_admin"}
      onLogout={sair}
    >
      <div className="flex flex-col gap-[18px]">
        <div className="flex items-start gap-3 rounded-lg border border-brand-200 bg-brand-50 px-4 py-3.5 text-[13px] text-brand-900">
          <BookIcon size={18} className="mt-0.5 flex-none text-brand-600" />
          <p>
            Os documentos enviados aqui são fragmentados e indexados para enriquecer as respostas
            do assistente sobre os <b>procedimentos desta escola</b>. Valem apenas para este
            tenant. Um documento <b>fora do ar</b> continua guardado, mas deixa de alimentar o
            assistente.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-[18px] lg:grid-cols-2">
          <NovoDocumento onMudou={recarregar} />
          <ListaDocumentos
            fontes={fontes}
            onMudou={recarregar}
            podeRemover={usuario.papel === "super_admin"}
          />
        </div>
      </div>
    </AppShell>
  );
}

function NovoDocumento({ onMudou }: { onMudou: () => Promise<void> }) {
  const toast = useToast();
  const [nome, setNome] = useState("");
  const [tipo, setTipo] = useState("procedimento");
  const [conteudo, setConteudo] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function lerArquivo(e: React.ChangeEvent<HTMLInputElement>) {
    const arquivo = e.target.files?.[0];
    if (!arquivo) return;
    const texto = await arquivo.text();
    setConteudo(texto);
    if (!nome.trim()) setNome(arquivo.name.replace(/\.[^.]+$/, ""));
  }

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim() || !conteudo.trim()) return;
    setSalvando(true);
    try {
      const fonte = await adicionarConhecimento(nome.trim(), conteudo, tipo);
      setNome("");
      setConteudo("");
      await onMudou();
      toast({
        tone: "success",
        title: "Documento indexado.",
        description: `"${fonte.nome}" · ${fonte.total_trechos} trecho(s).`,
      });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao enviar documento.",
      });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Enviar documento" />
      <form onSubmit={enviar} className="flex flex-col gap-3">
        <div className="flex flex-col gap-2 sm:flex-row">
          <Field label="Nome do documento" htmlFor="doc-nome">
            <Input
              id="doc-nome"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex.: Manual de matrícula"
            />
          </Field>
          <Field label="Tipo" htmlFor="doc-tipo">
            <Select id="doc-tipo" value={tipo} onChange={(e) => setTipo(e.target.value)}>
              {TIPOS.map((t) => (
                <option key={t.valor} value={t.valor}>
                  {t.rotulo}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <label className="flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border-[1.5px] border-dashed border-n-300 px-4 py-5 text-center hover:border-brand-400 hover:bg-brand-50/40">
          <FileIcon size={22} className="text-n-400" />
          <span className="text-[13px] font-semibold text-n-700">
            Carregar arquivo de texto (.txt/.md)
          </span>
          <span className="text-[11.5px] text-n-400">opcional — também pode colar abaixo</span>
          <input
            type="file"
            accept=".txt,.md,text/plain,text/markdown"
            onChange={lerArquivo}
            className="sr-only"
          />
        </label>

        <Textarea
          value={conteudo}
          onChange={(e) => setConteudo(e.target.value)}
          placeholder="Cole aqui o conteúdo do documento (procedimentos, regras, avisos)…"
          rows={9}
        />

        <Button type="submit" loading={salvando} className="self-start">
          {salvando ? "Indexando…" : "Indexar documento"}
        </Button>
      </form>
    </Card>
  );
}

function ListaDocumentos({
  fontes,
  onMudou,
  podeRemover,
}: {
  fontes: FonteConhecimento[];
  onMudou: () => Promise<void>;
  /** Só super admin apaga: é irreversível e destrói o texto original. */
  podeRemover: boolean;
}) {
  const toast = useToast();
  const [excluindo, setExcluindo] = useState<FonteConhecimento | null>(null);
  const [abrindo, setAbrindo] = useState<string | null>(null);
  const [editando, setEditando] = useState<FonteConhecimento | null>(null);

  async function confirmarExclusao() {
    if (!excluindo) return;
    try {
      await removerConhecimento(excluindo.id);
      setExcluindo(null);
      await onMudou();
      toast({ tone: "success", title: "Documento removido." });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao remover documento.",
      });
    }
  }

  async function abrir(fonte: FonteConhecimento) {
    setAbrindo(fonte.id);
    try {
      // A listagem não traz o texto; o detalhe traz.
      setEditando(await obterConhecimento(fonte.id));
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao abrir documento.",
      });
    } finally {
      setAbrindo(null);
    }
  }

  async function alternarAtivo(fonte: FonteConhecimento) {
    try {
      const nova = await definirAtivoConhecimento(fonte.id, !fonte.ativo);
      await onMudou();
      toast({
        tone: "success",
        title: nova.ativo ? "Documento de volta ao ar." : "Documento fora do ar.",
        description: nova.ativo
          ? "O assistente voltou a usá-lo nas respostas."
          : "O texto continua guardado, mas o assistente deixou de usá-lo.",
      });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao alterar o documento.",
      });
    }
  }

  return (
    <Card>
      <CardHeader title="Documentos indexados" count={fontes.length} />
      <div className="flex flex-col">
        {fontes.map((f) => (
          <div
            key={f.id}
            className="flex items-center gap-3 border-t border-n-100 py-3 first:border-t-0"
          >
            <div
              className={
                "flex h-9 w-9 flex-none items-center justify-center rounded-md " +
                (f.ativo ? "bg-brand-50 text-brand-600" : "bg-n-100 text-n-400")
              }
            >
              <FileIcon size={18} />
            </div>
            <button
              onClick={() => abrir(f)}
              disabled={abrindo === f.id}
              className="min-w-0 flex-1 text-left"
              title="Abrir para ler ou corrigir"
            >
              <p
                className={
                  "truncate text-[13px] font-semibold " +
                  (f.ativo ? "text-n-900" : "text-n-500")
                }
              >
                {f.nome}
              </p>
              <p className="mt-0.5 flex flex-wrap items-center gap-2 text-[11.5px] text-n-400">
                <Badge tone={f.ativo ? "brand" : "neutral"}>{f.tipo}</Badge>
                {!f.ativo && <Badge tone="warning">fora do ar</Badge>}
                {f.total_trechos} trecho(s) ·{" "}
                {new Date(f.criado_em).toLocaleDateString("pt-BR")}
              </p>
            </button>
            <div className="flex flex-none items-center gap-3">
              <button
                onClick={() => alternarAtivo(f)}
                className="text-xs font-semibold text-brand-600 hover:underline"
              >
                {f.ativo ? "Tirar do ar" : "Pôr no ar"}
              </button>
              {podeRemover && (
                <button
                  onClick={() => setExcluindo(f)}
                  className="text-xs font-semibold text-danger hover:underline"
                >
                  Remover
                </button>
              )}
            </div>
          </div>
        ))}
        {fontes.length === 0 && (
          <p className="py-2 text-sm text-n-400">Nenhum documento enviado ainda.</p>
        )}
      </div>

      {!podeRemover && fontes.length > 0 && (
        <p className="mt-3 border-t border-n-100 pt-3 text-[11.5px] text-n-400">
          A exclusão definitiva é feita pelo super admin da plataforma. Para tirar um
          procedimento do ar sem perder o texto, use <b>&ldquo;Tirar do ar&rdquo;</b>.
        </p>
      )}

      {editando && (
        <EditorDocumento
          fonte={editando}
          onFechar={() => setEditando(null)}
          onSalvo={async () => {
            setEditando(null);
            await onMudou();
          }}
        />
      )}

      <ConfirmDialog
        open={!!excluindo}
        onClose={() => setExcluindo(null)}
        onConfirm={confirmarExclusao}
        title="Remover documento"
        message={`Remover "${excluindo?.nome}" definitivamente? O texto original e os trechos indexados são apagados, e não há volta. Para apenas tirar do ar, use "Tirar do ar".`}
        confirmLabel="Remover"
      />
    </Card>
  );
}

function EditorDocumento({
  fonte,
  onFechar,
  onSalvo,
}: {
  fonte: FonteConhecimento;
  onFechar: () => void;
  onSalvo: () => Promise<void>;
}) {
  const toast = useToast();
  const [nome, setNome] = useState(fonte.nome);
  const [tipo, setTipo] = useState(fonte.tipo);
  const [conteudo, setConteudo] = useState(fonte.conteudo);
  const [salvando, setSalvando] = useState(false);

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim() || !conteudo.trim()) return;
    setSalvando(true);
    try {
      // O estado "no ar" é do interruptor da lista; salvar não o altera por acidente.
      await atualizarConhecimento(fonte.id, nome.trim(), conteudo, tipo, fonte.ativo);
      toast({
        tone: "success",
        title: "Documento salvo.",
        description: fonte.ativo
          ? "O assistente já responde com o texto novo."
          : "O texto foi guardado; o documento segue fora do ar.",
      });
      await onSalvo();
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao salvar documento.",
      });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal open onClose={onFechar} title={fonte.nome} className="max-w-3xl">
      <form onSubmit={salvar} className="flex flex-col gap-3">
        <div className="flex flex-col gap-2 sm:flex-row">
          <Field label="Nome do documento" htmlFor="edit-nome">
            <Input id="edit-nome" value={nome} onChange={(e) => setNome(e.target.value)} />
          </Field>
          <Field label="Tipo" htmlFor="edit-tipo">
            <Select id="edit-tipo" value={tipo} onChange={(e) => setTipo(e.target.value)}>
              {TIPOS.map((t) => (
                <option key={t.valor} value={t.valor}>
                  {t.rotulo}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <Field label="Conteúdo" htmlFor="edit-conteudo">
          <Textarea
            id="edit-conteudo"
            value={conteudo}
            onChange={(e) => setConteudo(e.target.value)}
            rows={16}
          />
        </Field>

        <div className="flex items-center justify-between gap-3 border-t border-n-100 pt-3.5">
          <span className="text-xs text-n-400">
            {fonte.ativo
              ? "Salvar reindexa o documento no assistente."
              : "Fora do ar: salvar guarda o texto, sem reindexar."}
          </span>
          <div className="flex flex-none gap-2">
            <Button type="button" variant="ghost" onClick={onFechar}>
              Cancelar
            </Button>
            <Button type="submit" loading={salvando}>
              {salvando ? "Salvando…" : "Salvar"}
            </Button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
