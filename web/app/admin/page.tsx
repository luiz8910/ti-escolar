"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  adicionarContato,
  consultarQuota,
  criarGrupo,
  enviarParaGrupo,
  getSessao,
  Grupo,
  logout,
  Quota,
  listarGrupos,
  ResultadoEnvioGrupo,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { QuotaBar } from "@/components/layout/QuotaBar";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/form";
import { TableWrap, Table, Th, Td, Tr } from "@/components/ui/Table";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import { UsersIcon, PlusIcon } from "@/components/ui/icons";

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
      tenantName="Escola Demonstração"
      isSuperAdmin={usuario.papel === "super_admin"}
      onLogout={sair}
    >
      <div className="flex flex-col gap-[18px]">
        {quota && (
          <QuotaBar enviados={quota.enviados} limite={quota.limite_diario} dia={quota.dia} />
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

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    if (!novo.trim()) return;
    try {
      await criarGrupo(novo.trim(), "");
      setNovo("");
      await onCriado();
      toast({ tone: "success", title: "Grupo criado." });
    } catch {
      toast({ tone: "danger", title: "Não foi possível criar o grupo." });
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
        <Button size="sm" type="submit" leftIcon={<PlusIcon size={15} />}>
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
  const [mensagem, setMensagem] = useState("");
  const [resultado, setResultado] = useState<ResultadoEnvioGrupo | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [adicionando, setAdicionando] = useState(false);

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
    if (!nome.trim() || !telefone.trim()) return;
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
    }
  }

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (!titulo.trim() || !mensagem.trim()) return;
    setEnviando(true);
    setResultado(null);
    try {
      const r = await enviarParaGrupo(grupo!.id, titulo.trim(), mensagem.trim());
      setResultado(r);
      setTitulo("");
      setMensagem("");
      await onMudou();
      toast({
        tone: "success",
        title: "Disparo concluído.",
        description: `${r.broadcast.enviados} enviados · ${r.broadcast.restante_cota} restantes na cota.`,
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
            <span className="font-semibold text-n-400">· {grupo.total_membros} contatos</span>
          </>
        }
        action={
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<PlusIcon size={14} />}
            onClick={() => setAdicionando((v) => !v)}
          >
            Contato
          </Button>
        }
      />

      <TableWrap>
        <Table>
          <thead>
            <tr>
              <Th>Responsável</Th>
              <Th>WhatsApp</Th>
            </tr>
          </thead>
          <tbody>
            {grupo.membros.map((c) => (
              <Tr key={c.id}>
                <Td className="font-medium">{c.nome}</Td>
                <Td className="font-mono text-xs text-n-500">{c.telefone}</Td>
              </Tr>
            ))}
            {grupo.membros.length === 0 && (
              <Tr>
                <Td colSpan={2} className="text-n-400">
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
          <Input
            className="w-44"
            mono
            value={telefone}
            onChange={(e) => setTelefone(e.target.value)}
            placeholder="+5511999990000"
          />
          <Button variant="secondary" size="sm" type="submit">
            Adicionar
          </Button>
        </form>
      )}

      <div className="mt-[18px] border-t border-n-100 pt-4">
        <h4 className="text-sm font-bold text-n-900">Enviar mensagem ao grupo</h4>
        <p className="mt-1 text-xs text-n-500">
          Usa o template aprovado e respeita a cota diária. Alcança apenas os{" "}
          {grupo.total_membros} contato(s) de <b>{grupo.nome}</b>.
        </p>
        <form onSubmit={enviar} className="mt-3 flex flex-col gap-2.5">
          <Input
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="Título (ex.: Reunião de pais)"
          />
          <Textarea
            rows={3}
            value={mensagem}
            onChange={(e) => setMensagem(e.target.value)}
            placeholder="Mensagem aos responsáveis…"
          />
          <Button type="submit" loading={enviando} className="self-start">
            {enviando ? "Enviando…" : `Enviar para ${grupo.total_membros} contatos`}
          </Button>
        </form>

        {resultado && (
          <div className="mt-4 rounded-md bg-success-soft p-3 text-[13px] text-success">
            ✓ Disparo concluído — <b>{resultado.broadcast.enviados}</b> enviados
            {resultado.broadcast.falhas > 0 && `, ${resultado.broadcast.falhas} falhas`}
            {resultado.broadcast.bloqueados_por_limite > 0 &&
              `, ${resultado.broadcast.bloqueados_por_limite} bloqueados pela cota`}
            . Restam {resultado.broadcast.restante_cota} na cota de hoje.
          </div>
        )}
      </div>
    </Card>
  );
}
