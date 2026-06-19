"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  atualizarEscola,
  bloquearEscola,
  criarEscola,
  definirLicenca,
  desbloquearEscola,
  Escola,
  getSessao,
  listarEscolas,
  logout,
  notificarVencimento,
  removerEscola,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Field, Select, Textarea } from "@/components/ui/form";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { LicencaBadge } from "@/components/admin/LicencaBadge";
import {
  PlusIcon,
  ExternalIcon,
  ChatBubbleIcon,
  UsersIcon,
  BellIcon,
} from "@/components/ui/icons";

function sigla(nome: string) {
  return nome
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export default function EscolasPage() {
  const router = useRouter();
  const toast = useToast();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [escolas, setEscolas] = useState<Escola[]>([]);
  const [carregando, setCarregando] = useState(true);

  const recarregar = useCallback(async () => {
    setEscolas(await listarEscolas());
  }, []);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    if (s.usuario.papel !== "super_admin") {
      router.replace("/admin");
      return;
    }
    setUsuario(s.usuario);
    recarregar()
      .catch(() => toast({ tone: "danger", title: "Falha ao carregar escolas." }))
      .finally(() => setCarregando(false));
  }, [router, recarregar, toast]);

  function sair() {
    logout();
    router.replace("/admin/login");
  }

  if (!usuario) return null;

  return (
    <AppShell
      title="Escolas"
      user={{ name: usuario.nome, role: "Super Admin" }}
      tenantName="Plataforma"
      isSuperAdmin
      onLogout={sair}
    >
      <div className="flex flex-col gap-[18px]">
        <NovaEscola onCriada={recarregar} />

        <Card>
          <CardHeader
            title="Escolas cadastradas"
            count={escolas.length}
            action={<AvisarVencimentos />}
          />
          {carregando ? (
            <p className="text-sm text-n-400">Carregando…</p>
          ) : escolas.length === 0 ? (
            <p className="text-sm text-n-400">Nenhuma escola cadastrada ainda.</p>
          ) : (
            <div className="flex flex-col">
              {escolas.map((e) => (
                <EscolaLinha key={e.id} escola={e} onMudou={recarregar} />
              ))}
            </div>
          )}
        </Card>
      </div>
    </AppShell>
  );
}

function AvisarVencimentos() {
  const toast = useToast();
  const [enviando, setEnviando] = useState(false);

  async function avisar() {
    setEnviando(true);
    try {
      const avisos = await notificarVencimento();
      toast({
        tone: "success",
        title: avisos.length
          ? `${avisos.length} escola(s) avisada(s) por e-mail.`
          : "Nenhuma licença anual perto do vencimento.",
      });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao avisar." });
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Button variant="secondary" size="sm" loading={enviando} onClick={avisar}>
      Avisar vencimentos
    </Button>
  );
}

function NovaEscola({ onCriada }: { onCriada: () => Promise<void> }) {
  const toast = useToast();
  const [nome, setNome] = useState("");
  const [slug, setSlug] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim()) return;
    setSalvando(true);
    try {
      await criarEscola(nome.trim(), slug.trim());
      setNome("");
      setSlug("");
      await onCriada();
      toast({ tone: "success", title: "Escola cadastrada." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao criar escola." });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Cadastrar escola" />
      <form onSubmit={criar} className="flex flex-wrap items-end gap-3">
        <div className="min-w-[200px] flex-1">
          <Field label="Nome" htmlFor="esc-nome">
            <Input
              id="esc-nome"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex.: Colégio São José"
            />
          </Field>
        </div>
        <div className="min-w-[180px]">
          <Field label="Slug (opcional)" htmlFor="esc-slug">
            <Input
              id="esc-slug"
              mono
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="derivado do nome"
            />
          </Field>
        </div>
        <Button type="submit" loading={salvando} leftIcon={<PlusIcon size={15} />}>
          {salvando ? "Salvando…" : "Cadastrar"}
        </Button>
      </form>
    </Card>
  );
}

function EscolaLinha({ escola, onMudou }: { escola: Escola; onMudou: () => Promise<void> }) {
  const router = useRouter();
  const toast = useToast();
  const [editando, setEditando] = useState(false);
  const [excluindo, setExcluindo] = useState(false);
  const [bloqueando, setBloqueando] = useState(false);
  const [editandoLicenca, setEditandoLicenca] = useState(false);
  const [nome, setNome] = useState(escola.nome);
  const [slug, setSlug] = useState(escola.slug);
  const bloqueada = escola.licenca.status === "bloqueado";

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    try {
      await atualizarEscola(escola.id, nome.trim(), slug.trim());
      setEditando(false);
      await onMudou();
      toast({ tone: "success", title: "Escola atualizada." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao salvar." });
    }
  }

  async function confirmarExclusao() {
    try {
      await removerEscola(escola.id);
      setExcluindo(false);
      await onMudou();
      toast({ tone: "success", title: "Escola excluída." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao excluir." });
    }
  }

  async function desbloquear() {
    try {
      await desbloquearEscola(escola.id);
      await onMudou();
      toast({ tone: "success", title: "Escola desbloqueada." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao desbloquear." });
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3 border-t border-n-100 py-3.5 first:border-t-0">
      <div className="flex h-10 w-10 flex-none items-center justify-center rounded-[11px] bg-gradient-to-br from-brand-500 to-brand-700 text-[13px] font-bold text-white">
        {sigla(escola.nome)}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <Link
            href={`/admin/escolas/${escola.id}`}
            className="text-sm font-bold text-n-900 hover:text-brand-700 hover:underline"
          >
            {escola.nome}
          </Link>
          <LicencaBadge licenca={escola.licenca} />
        </div>
        <p className="font-mono text-[11.5px] text-n-400">{escola.slug}</p>
      </div>

      <div className="flex items-center gap-4 text-[11.5px] font-semibold text-n-500">
        <span className="flex items-center gap-1" title="Conversas">
          <ChatBubbleIcon size={15} /> {escola.total_conversas}
        </span>
        <span className="flex items-center gap-1" title="Contatos">
          <UsersIcon size={15} /> {escola.total_contatos}
        </span>
        <span className="flex items-center gap-1" title="Mensagens em massa">
          <BellIcon size={15} /> {escola.total_broadcasts}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          leftIcon={<ExternalIcon size={14} />}
          onClick={() => router.push(`/admin/escolas/${escola.id}`)}
        >
          Abrir
        </Button>
        <Button variant="secondary" size="sm" onClick={() => setEditando(true)}>
          Editar
        </Button>
        <Button variant="secondary" size="sm" onClick={() => setEditandoLicenca(true)}>
          Licença
        </Button>
        {bloqueada ? (
          <Button variant="secondary" size="sm" onClick={desbloquear}>
            Desbloquear
          </Button>
        ) : (
          <Button variant="secondary" size="sm" onClick={() => setBloqueando(true)}>
            Bloquear
          </Button>
        )}
        <Button variant="danger" size="sm" onClick={() => setExcluindo(true)}>
          Excluir
        </Button>
      </div>

      <Modal
        open={editando}
        onClose={() => setEditando(false)}
        title="Editar escola"
        footer={
          <>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setEditando(false);
                setNome(escola.nome);
                setSlug(escola.slug);
              }}
            >
              Cancelar
            </Button>
            <Button size="sm" onClick={salvar}>
              Salvar
            </Button>
          </>
        }
      >
        <form onSubmit={salvar} className="flex flex-col gap-3">
          <Field label="Nome">
            <Input autoFocus value={nome} onChange={(e) => setNome(e.target.value)} />
          </Field>
          <Field label="Slug">
            <Input mono value={slug} onChange={(e) => setSlug(e.target.value)} />
          </Field>
        </form>
      </Modal>

      <ConfirmDialog
        open={excluindo}
        onClose={() => setExcluindo(false)}
        onConfirm={confirmarExclusao}
        title="Excluir escola"
        message={`Excluir "${escola.nome}" e TODOS os seus dados (conversas, contatos, mensagens)? Esta ação é irreversível.`}
      />

      <BloquearModal
        escola={escola}
        open={bloqueando}
        onClose={() => setBloqueando(false)}
        onMudou={onMudou}
      />

      <LicencaModal
        escola={escola}
        open={editandoLicenca}
        onClose={() => setEditandoLicenca(false)}
        onMudou={onMudou}
      />
    </div>
  );
}

// Converte ISO (com hora) -> "YYYY-MM-DD" para o input[type=date]; "" se vazio.
function paraInputData(iso: string | null): string {
  return iso ? iso.slice(0, 10) : "";
}

function BloquearModal({
  escola,
  open,
  onClose,
  onMudou,
}: {
  escola: Escola;
  open: boolean;
  onClose: () => void;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [motivo, setMotivo] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function confirmar() {
    if (!motivo.trim()) {
      toast({ tone: "danger", title: "Informe o motivo do bloqueio." });
      return;
    }
    setSalvando(true);
    try {
      await bloquearEscola(escola.id, motivo.trim());
      setMotivo("");
      onClose();
      await onMudou();
      toast({ tone: "success", title: "Escola bloqueada." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao bloquear." });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Bloquear "${escola.nome}"`}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancelar
          </Button>
          <Button variant="danger" size="sm" loading={salvando} onClick={confirmar}>
            Bloquear
          </Button>
        </>
      }
    >
      <p className="mb-3 text-sm text-n-500">
        A escola perde acesso ao painel e aos disparos até ser desbloqueada. O motivo fica
        registrado.
      </p>
      <Field label="Motivo do bloqueio">
        <Textarea
          autoFocus
          rows={3}
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
          placeholder="Ex.: Inadimplência — mensalidade de junho/2026 em aberto."
        />
      </Field>
    </Modal>
  );
}

function LicencaModal({
  escola,
  open,
  onClose,
  onMudou,
}: {
  escola: Escola;
  open: boolean;
  onClose: () => void;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [plano, setPlano] = useState<"mensal" | "anual">(escola.licenca.plano);
  const [expira, setExpira] = useState(paraInputData(escola.licenca.licenca_expira_em));
  const [salvando, setSalvando] = useState(false);

  async function salvar() {
    setSalvando(true);
    try {
      // input[type=date] devolve "YYYY-MM-DD"; envia null se vazio.
      await definirLicenca(escola.id, plano, expira ? `${expira}T00:00:00Z` : null);
      onClose();
      await onMudou();
      toast({ tone: "success", title: "Licença atualizada." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao salvar." });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Licença de "${escola.nome}"`}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancelar
          </Button>
          <Button size="sm" loading={salvando} onClick={salvar}>
            Salvar
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label="Plano">
          <Select value={plano} onChange={(e) => setPlano(e.target.value as "mensal" | "anual")}>
            <option value="mensal">Mensal</option>
            <option value="anual">Anual</option>
          </Select>
        </Field>
        <Field label="Expira em">
          <Input type="date" value={expira} onChange={(e) => setExpira(e.target.value)} />
        </Field>
        <p className="text-xs text-n-400">
          No plano anual, a plataforma avisa os admins por e-mail quando a licença está perto de
          vencer.
        </p>
      </div>
    </Modal>
  );
}
