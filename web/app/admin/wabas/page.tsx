"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  atualizarContaWhatsApp,
  ContaWhatsApp,
  criarContaWhatsApp,
  getSessao,
  listarContasWhatsApp,
  logout,
  removerContaWhatsApp,
  replicarTemplates,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input, Field } from "@/components/ui/form";
import { TableWrap, Table, Th, Td, Tr } from "@/components/ui/Table";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { PlusIcon } from "@/components/ui/icons";

/** Teto de números por portfólio, segundo a doc da Meta (2 iniciais, 20 após verificação).
 *
 * Fica aqui como **referência de tela**, não como regra: quem impõe o limite é a Meta, e
 * ela o eleva sob pedido. O valor serve para a barra de ocupação avisar antes, em vez de o
 * teto aparecer como erro da Graph API no meio de um cadastro. */
const LIMITE_NUMEROS = 20;

export default function ContasWhatsApp() {
  const router = useRouter();
  const toast = useToast();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [contas, setContas] = useState<ContaWhatsApp[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [criando, setCriando] = useState(false);

  const recarregar = useCallback(async () => {
    setContas(await listarContasWhatsApp());
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
      .catch(() => toast({ tone: "danger", title: "Falha ao carregar as contas." }))
      .finally(() => setCarregando(false));
  }, [router, recarregar, toast]);

  if (!usuario) return null;

  return (
    <AppShell
      exigeEscola={false}
      title="Contas do WhatsApp (WABA)"
      user={{ name: usuario.nome, role: "Super Admin" }}
      isSuperAdmin
      onLogout={() => {
        logout();
        router.replace("/admin/login");
      }}
    >
      <div className="flex flex-col gap-[18px]">
        <Explicacao />
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" leftIcon={<PlusIcon size={15} />} onClick={() => setCriando(true)}>
            Nova conta
          </Button>
          <BotaoReplicar onMudou={recarregar} />
        </div>

        <Card>
          <CardHeader title="Contas cadastradas" count={contas.length} />
          {carregando ? (
            <p className="text-sm text-n-400">Carregando…</p>
          ) : contas.length === 0 ? (
            <p className="text-sm text-n-400">
              Nenhuma conta cadastrada. Sem conta, nenhum template pode ser criado.
            </p>
          ) : (
            <TableWrap>
              <Table>
                <thead>
                  <tr>
                    <Th>Nome</Th>
                    <Th>Id na Meta</Th>
                    <Th>Portfólio</Th>
                    <Th>Escolas</Th>
                    <Th>Situação</Th>
                    <Th className="text-right">Ações</Th>
                  </tr>
                </thead>
                <tbody>
                  {contas.map((c) => (
                    <Linha key={c.id} conta={c} onMudou={recarregar} />
                  ))}
                </tbody>
              </Table>
            </TableWrap>
          )}
        </Card>
      </div>

      {criando && (
        <Formulario
          onFechar={() => setCriando(false)}
          onSalvo={async () => {
            setCriando(false);
            await recarregar();
          }}
        />
      )}
    </AppShell>
  );
}

function Explicacao() {
  return (
    <Card>
      <CardHeader title="Por que existe mais de uma conta" />
      <div className="flex flex-col gap-2 text-xs text-n-500">
        <p>
          Cada escola opera com um número dedicado, e o cadastro de números tem{" "}
          <strong>teto no portfólio</strong> da Meta ({LIMITE_NUMEROS} após a verificação da
          empresa). Ao esgotá-lo, a escola seguinte entra em outra conta.
        </p>
        <p>
          Isso importa porque <strong>template é aprovado por conta</strong>: o{" "}
          <code>aviso_geral</code> aprovado aqui não existe na conta ao lado. Por isso cada
          escola declara em qual conta o número dela está — é onde o template dela é criado
          e onde a aprovação é conferida antes de um disparo.
        </p>
        <p>
          Ao cadastrar uma conta nova, use <strong>&quot;Replicar templates globais&quot;</strong>:
          sem isso, as escolas dela ficam sem nenhum template aprovado, e a falha só aparece
          no primeiro disparo.
        </p>
      </div>
    </Card>
  );
}

function BotaoReplicar({ onMudou }: { onMudou: () => Promise<void> }) {
  const toast = useToast();
  const [rodando, setRodando] = useState(false);

  async function replicar() {
    setRodando(true);
    try {
      const r = await replicarTemplates();
      await onMudou();
      toast({
        tone: r.falhas > 0 ? "danger" : "success",
        title:
          r.submetidos > 0
            ? `${r.submetidos} submissão(ões) enviada(s) à Meta.`
            : "Todas as contas já têm os templates globais.",
        description:
          r.falhas > 0 ? `${r.falhas} falharam — tente de novo mais tarde.` : undefined,
      });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao replicar.",
      });
    } finally {
      setRodando(false);
    }
  }

  return (
    <Button size="sm" variant="secondary" onClick={replicar} disabled={rodando}>
      {rodando ? "Submetendo…" : "Replicar templates globais"}
    </Button>
  );
}

function Linha({ conta, onMudou }: { conta: ContaWhatsApp; onMudou: () => Promise<void> }) {
  const toast = useToast();
  const [editando, setEditando] = useState(false);
  const [excluindo, setExcluindo] = useState(false);
  const lotada = conta.total_escolas >= LIMITE_NUMEROS;

  async function confirmarExclusao() {
    try {
      await removerContaWhatsApp(conta.id);
      setExcluindo(false);
      await onMudou();
      toast({ tone: "success", title: "Conta removida." });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao remover.",
      });
    }
  }

  return (
    <>
      <Tr>
        <Td className="text-xs font-medium text-n-900">{conta.nome}</Td>
        <Td className="font-mono text-xs">
          {conta.meta_waba_id || (
            <span className="text-amber-600" title="Sem o id da Meta não há onde criar template.">
              ⚠ sem id
            </span>
          )}
        </Td>
        <Td className="font-mono text-[11px] text-n-500">{conta.meta_business_id || "—"}</Td>
        <Td className="text-xs">
          <span className={lotada ? "font-semibold text-danger" : ""}>
            {conta.total_escolas} / {LIMITE_NUMEROS}
          </span>
          {lotada && (
            <span className="ml-1 text-[11px] text-danger">no teto</span>
          )}
        </Td>
        <Td>
          {conta.ativo ? (
            <Badge tone="success" dot>
              Ativa
            </Badge>
          ) : (
            <Badge tone="neutral">Inativa</Badge>
          )}
        </Td>
        <Td className="text-right">
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="secondary" onClick={() => setEditando(true)}>
              Editar
            </Button>
            <Button size="sm" variant="danger" onClick={() => setExcluindo(true)}>
              Excluir
            </Button>
          </div>
        </Td>
      </Tr>

      {editando && (
        <Formulario
          conta={conta}
          onFechar={() => setEditando(false)}
          onSalvo={async () => {
            setEditando(false);
            await onMudou();
          }}
        />
      )}

      <ConfirmDialog
        open={excluindo}
        title={`Excluir "${conta.nome}"?`}
        message="Só é possível remover conta sem escolas. Para parar de usá-la mantendo o histórico, desative-a em vez de excluir."
        confirmLabel="Excluir"
        onClose={() => setExcluindo(false)}
        onConfirm={confirmarExclusao}
      />
    </>
  );
}

function Formulario({
  conta,
  onFechar,
  onSalvo,
}: {
  conta?: ContaWhatsApp;
  onFechar: () => void;
  onSalvo: () => Promise<void>;
}) {
  const toast = useToast();
  const [nome, setNome] = useState(conta?.nome ?? "");
  const [metaWabaId, setMetaWabaId] = useState(conta?.meta_waba_id ?? "");
  const [metaBusinessId, setMetaBusinessId] = useState(conta?.meta_business_id ?? "");
  const [ativo, setAtivo] = useState(conta?.ativo ?? true);
  const [salvando, setSalvando] = useState(false);

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim()) {
      toast({ tone: "danger", title: "Dê um nome à conta." });
      return;
    }
    setSalvando(true);
    try {
      const dados = {
        nome: nome.trim(),
        meta_waba_id: metaWabaId.trim(),
        meta_business_id: metaBusinessId.trim(),
        ativo,
      };
      if (conta) await atualizarContaWhatsApp(conta.id, dados);
      else await criarContaWhatsApp(dados);
      await onSalvo();
      toast({ tone: "success", title: conta ? "Conta atualizada." : "Conta cadastrada." });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao salvar.",
      });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      open
      onClose={onFechar}
      title={conta ? `Editar ${conta.nome}` : "Nova conta do WhatsApp"}
      footer={
        <>
          <Button variant="secondary" onClick={onFechar}>
            Cancelar
          </Button>
          <Button onClick={salvar} loading={salvando}>
            Salvar
          </Button>
        </>
      }
    >
      <form onSubmit={salvar} className="flex flex-col gap-3">
        <Field label="Nome (como aparece no painel)">
          <Input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder="Ex.: WABA principal"
          />
        </Field>
        <Field label="Id da WABA na Meta">
          <Input
            mono
            value={metaWabaId}
            onChange={(e) => setMetaWabaId(e.target.value)}
            placeholder="2116419572321695"
          />
          <p className="mt-1 text-[11.5px] leading-snug text-n-500">
            Está no WhatsApp Manager, em Configurações da conta. É o endereço usado para
            criar e listar os templates desta conta — sem ele, nenhum template pode ser
            submetido aqui.
          </p>
        </Field>
        <Field label="Id do portfólio empresarial (opcional)">
          <Input
            mono
            value={metaBusinessId}
            onChange={(e) => setMetaBusinessId(e.target.value)}
            placeholder="940840332344260"
          />
          <p className="mt-1 text-[11.5px] leading-snug text-n-500">
            O portfólio dono da conta. É nele que a Meta mede o teto de números e o limite
            diário de envio — que são <strong>compartilhados</strong> por todas as contas do
            mesmo portfólio.
          </p>
        </Field>
        <label className="flex items-center gap-2 text-sm text-n-700">
          <input
            type="checkbox"
            checked={ativo}
            onChange={(e) => setAtivo(e.target.checked)}
            className="h-4 w-4 accent-brand-600"
          />
          Ativa (recebe replicação de template e pode ser escolhida em escola nova)
        </label>
      </form>
    </Modal>
  );
}
