"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  adicionarConhecimento,
  FonteConhecimento,
  getSessao,
  listarConhecimento,
  logout,
  removerConhecimento,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select, Textarea, Field } from "@/components/ui/form";
import { Badge } from "@/components/ui/Badge";
import { ConfirmDialog } from "@/components/ui/Modal";
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
      tenantName="Escola Demonstração"
      isSuperAdmin={usuario.papel === "super_admin"}
      onLogout={sair}
    >
      <div className="flex flex-col gap-[18px]">
        <div className="flex items-start gap-3 rounded-lg border border-brand-200 bg-brand-50 px-4 py-3.5 text-[13px] text-brand-900">
          <BookIcon size={18} className="mt-0.5 flex-none text-brand-600" />
          <p>
            Os documentos enviados aqui são fragmentados e indexados para enriquecer as respostas
            do assistente sobre os <b>procedimentos desta escola</b>. Valem apenas para este tenant.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-[18px] lg:grid-cols-2">
          <NovoDocumento onMudou={recarregar} />
          <ListaDocumentos fontes={fontes} onMudou={recarregar} />
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
}: {
  fontes: FonteConhecimento[];
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [excluindo, setExcluindo] = useState<FonteConhecimento | null>(null);

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

  return (
    <Card>
      <CardHeader title="Documentos indexados" count={fontes.length} />
      <div className="flex flex-col">
        {fontes.map((f) => (
          <div
            key={f.id}
            className="flex items-center gap-3 border-t border-n-100 py-3 first:border-t-0"
          >
            <div className="flex h-9 w-9 flex-none items-center justify-center rounded-md bg-brand-50 text-brand-600">
              <FileIcon size={18} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-semibold text-n-900">{f.nome}</p>
              <p className="mt-0.5 flex items-center gap-2 text-[11.5px] text-n-400">
                <Badge tone="brand">{f.tipo}</Badge>
                {f.total_trechos} trecho(s) · {new Date(f.criado_em).toLocaleDateString("pt-BR")}
              </p>
            </div>
            <button
              onClick={() => setExcluindo(f)}
              className="text-xs font-semibold text-danger hover:underline"
            >
              Remover
            </button>
          </div>
        ))}
        {fontes.length === 0 && (
          <p className="py-2 text-sm text-n-400">Nenhum documento enviado ainda.</p>
        )}
      </div>

      <ConfirmDialog
        open={!!excluindo}
        onClose={() => setExcluindo(null)}
        onConfirm={confirmarExclusao}
        title="Remover documento"
        message={`Remover "${excluindo?.nome}" da base de conhecimento? Os trechos indexados serão apagados.`}
        confirmLabel="Remover"
      />
    </Card>
  );
}
