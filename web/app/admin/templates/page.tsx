"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  criarTemplate,
  exigeEscolhaDeEscola,
  getSessao,
  listarTemplates,
  logout,
  placeholdersDoCorpo,
  problemaNoCorpoDoTemplate,
  removerTemplate,
  sincronizarTemplates,
  TemplateMensagem,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/form";
import { TableWrap, Table, Th, Td, Tr } from "@/components/ui/Table";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { Badge } from "@/components/ui/Badge";
import { useToast } from "@/components/ui/Toast";
import { PlusIcon } from "@/components/ui/icons";

export default function Templates() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [itens, setItens] = useState<TemplateMensagem[]>([]);
  const [criando, setCriando] = useState(false);
  const toast = useToast();

  const recarregar = useCallback(async () => {
    setItens(await listarTemplates());
  }, []);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    if (exigeEscolhaDeEscola()) return;
    recarregar().catch(() =>
      toast({ tone: "danger", title: "Falha ao carregar os templates." })
    );
  }, [router, recarregar, toast]);

  if (!usuario) return null;
  const superAdmin = usuario.papel === "super_admin";

  return (
    <AppShell
      title="Templates de mensagem"
      user={{
        name: usuario.nome,
        role: superAdmin ? "Super Admin" : "Admin da escola",
      }}
      isSuperAdmin={superAdmin}
      onLogout={() => {
        logout();
        router.replace("/admin/login");
      }}
    >
      <div className="flex flex-col gap-[18px]">
        <Explicacao />
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" leftIcon={<PlusIcon size={15} />} onClick={() => setCriando(true)}>
            Novo template
          </Button>
          {superAdmin && <BotaoSincronizar onMudou={recarregar} />}
        </div>
        <Lista itens={itens} superAdmin={superAdmin} onMudou={recarregar} />
      </div>

      {criando && (
        <NovoTemplate
          podeCriarGlobal={superAdmin}
          onFechar={() => setCriando(false)}
          onCriado={async () => {
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
      <CardHeader title="Como funcionam os templates" />
      <div className="flex flex-col gap-2 text-xs text-n-500">
        <p>
          Fora da janela de 24h (quando o responsável não escreveu para a escola
          recentemente), o WhatsApp só entrega <strong>template aprovado pela Meta</strong>.
          O template é a <em>forma</em> da mensagem: o texto variável entra como parâmetro
          no envio, então o mesmo <code>aviso_geral</code> serve para reunião, feira de
          ciências e recesso — muda só o conteúdo das variáveis.
        </p>
        <p>
          <strong>Global</strong> é o catálogo compartilhado entre as escolas: aprovado uma
          vez, usado por todas, com o nome da escola como variável. <strong>Da escola</strong>{" "}
          é o específico dela, e o nome recebe o prefixo do slug para não colidir.
        </p>
        <p>
          A revisão da Meta é <strong>assíncrona</strong> — leva de minutos a cerca de 24h.
          Enquanto o status não for <em>aprovado</em>, o disparo com esse template é
          recusado.
        </p>
      </div>
    </Card>
  );
}

function BotaoSincronizar({ onMudou }: { onMudou: () => Promise<void> }) {
  const toast = useToast();
  const [rodando, setRodando] = useState(false);

  async function sincronizar() {
    setRodando(true);
    try {
      const r = await sincronizarTemplates();
      await onMudou();
      toast({
        tone: "success",
        title: `${r.atualizados} template(s) atualizado(s) de ${r.verificados} na Meta.`,
        description:
          r.desconhecidos > 0
            ? `${r.desconhecidos} existe(m) na Meta e não no catálogo (criado(s) direto no WhatsApp Manager).`
            : undefined,
      });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao sincronizar.",
      });
    } finally {
      setRodando(false);
    }
  }

  return (
    <Button size="sm" variant="secondary" onClick={sincronizar} disabled={rodando}>
      {rodando ? "Consultando a Meta…" : "Sincronizar com a Meta"}
    </Button>
  );
}

function StatusBadge({ t }: { t: TemplateMensagem }) {
  if (t.status === "aprovado")
    return (
      <Badge tone="success" dot>
        Aprovado
      </Badge>
    );
  if (t.status === "pendente")
    return (
      <Badge tone="warning" dot>
        Em análise
      </Badge>
    );
  if (t.status === "rejeitado")
    return (
      <Badge tone="danger" dot>
        Rejeitado
      </Badge>
    );
  return <Badge tone="neutral">Rascunho</Badge>;
}

/** O status conta a conta.

Com uma conta só, repetir o selo seria ruído — então não aparece. A partir da segunda é o
detalhe que importa: "aprovado" no consolidado esconde qual escola pode disparar, porque o
que libera o envio de uma escola é a aprovação **na conta dela**. */
function PorConta({ t }: { t: TemplateMensagem }) {
  if (t.contas.length < 2) return null;
  return (
    <div className="mt-1 flex flex-col gap-0.5">
      {t.contas.map((c) => (
        <span key={c.waba_id} className="text-[11px] text-n-500">
          {c.waba_nome}: <span className="font-medium">{ROTULO_STATUS[c.status] ?? c.status}</span>
        </span>
      ))}
    </div>
  );
}

const ROTULO_STATUS: Record<string, string> = {
  aprovado: "aprovado",
  pendente: "em análise",
  rejeitado: "rejeitado",
  rascunho: "não submetido",
};

function Lista({
  itens,
  superAdmin,
  onMudou,
}: {
  itens: TemplateMensagem[];
  superAdmin: boolean;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [excluindo, setExcluindo] = useState<TemplateMensagem | null>(null);

  async function confirmarExclusao() {
    if (!excluindo) return;
    try {
      await removerTemplate(excluindo.id);
      setExcluindo(null);
      await onMudou();
      toast({ tone: "success", title: "Template removido daqui e da Meta." });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao remover.",
      });
    }
  }

  return (
    <Card>
      <CardHeader title={`Templates (${itens.length})`} />
      {itens.length === 0 ? (
        <p className="text-sm text-n-500">
          Nenhum template no catálogo ainda. Crie um acima ou sincronize com a Meta.
        </p>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Nome</Th>
                <Th>Escopo</Th>
                <Th>Corpo</Th>
                <Th>Categoria</Th>
                <Th>Status</Th>
                <Th className="text-right">Ações</Th>
              </tr>
            </thead>
            <tbody>
              {itens.map((t) => {
                // Global só o super admin remove: é ativo compartilhado entre as escolas.
                const podeRemover = superAdmin || t.escopo === "escola";
                return (
                  <Tr key={t.id}>
                    <Td className="font-mono text-xs font-medium">{t.nome}</Td>
                    <Td>
                      <Badge tone={t.escopo === "global" ? "brand" : "neutral"}>
                        {t.escopo === "global" ? "Global" : "Da escola"}
                      </Badge>
                    </Td>
                    <Td className="max-w-[380px] text-xs text-n-600">
                      <span className="line-clamp-2">{t.corpo}</span>
                      {t.contas
                        .filter((c) => c.motivo_rejeicao)
                        .map((c) => (
                          <span
                            key={c.waba_id}
                            className="mt-1 block text-[11px] text-danger"
                          >
                            Meta ({c.waba_nome}): {c.motivo_rejeicao}
                          </span>
                        ))}
                    </Td>
                    <Td className="text-xs">
                      {t.categoria}
                      {t.categoria === "marketing" && (
                        <span className="ml-1 text-[11px] text-warning">(mais caro)</span>
                      )}
                    </Td>
                    <Td>
                      <StatusBadge t={t} />
                      <PorConta t={t} />
                    </Td>
                    <Td className="text-right">
                      {podeRemover ? (
                        <Button size="sm" variant="danger" onClick={() => setExcluindo(t)}>
                          Excluir
                        </Button>
                      ) : (
                        <span className="text-[11px] text-n-400">catálogo compartilhado</span>
                      )}
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
        </TableWrap>
      )}

      {excluindo && (
        <ConfirmDialog
          open
          title={`Excluir "${excluindo.nome}"?`}
          message="O template é apagado aqui e na Meta. Disparos que dependem dele param de funcionar, e recriar exige nova aprovação."
          confirmLabel="Excluir"
          onClose={() => setExcluindo(null)}
          onConfirm={confirmarExclusao}
        />
      )}
    </Card>
  );
}

function NovoTemplate({
  podeCriarGlobal,
  onFechar,
  onCriado,
}: {
  podeCriarGlobal: boolean;
  onFechar: () => void;
  onCriado: () => Promise<void>;
}) {
  const toast = useToast();
  const [nome, setNome] = useState("");
  const [corpo, setCorpo] = useState("");
  const [categoria, setCategoria] = useState("utility");
  const [global, setGlobal] = useState(podeCriarGlobal);
  const [exemplos, setExemplos] = useState<string[]>([]);
  const [enviando, setEnviando] = useState(false);

  const placeholders = useMemo(() => placeholdersDoCorpo(corpo), [corpo]);
  const problema = useMemo(() => problemaNoCorpoDoTemplate(corpo), [corpo]);

  // Um campo de exemplo por variável: a Meta recusa template com variável e sem amostra.
  useEffect(() => {
    setExemplos((atuais) =>
      placeholders.map((_, i) => atuais[i] ?? "")
    );
  }, [placeholders.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const faltaExemplo = placeholders.length > 0 && exemplos.some((e) => !e.trim());
  const podeEnviar = !!nome.trim() && !problema && !faltaExemplo && !enviando;

  const previa = useMemo(() => {
    let texto = corpo;
    placeholders.forEach((n, i) => {
      texto = texto.replaceAll(`{{${n}}}`, exemplos[i]?.trim() || `{{${n}}}`);
    });
    return texto;
  }, [corpo, placeholders, exemplos]);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (!podeEnviar) return;
    setEnviando(true);
    try {
      await criarTemplate({
        nome: nome.trim(),
        corpo: corpo.trim(),
        categoria,
        exemplos: exemplos.map((x) => x.trim()),
        global,
      });
      toast({
        tone: "success",
        title: "Template enviado para a Meta.",
        description: "A revisão é assíncrona; o status muda sozinho quando ela concluir.",
      });
      await onCriado();
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao criar o template.",
      });
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Modal open title="Novo template" onClose={onFechar}>
      <form onSubmit={enviar} className="flex flex-col gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-n-600">Nome</label>
          <Input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder="aviso_geral"
          />
          <p className="mt-1 text-[11px] text-n-400">
            Só minúsculas sem acento, números e sublinhado.
            {!global && " O slug da escola é acrescentado como prefixo."}
          </p>
        </div>

        {podeCriarGlobal && (
          <label className="flex items-start gap-2 text-xs text-n-600">
            <input
              type="checkbox"
              checked={global}
              onChange={(e) => setGlobal(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              <strong>Global</strong> — catálogo compartilhado entre todas as escolas. Use o
              nome da escola como variável no corpo.
            </span>
          </label>
        )}

        <div>
          <label className="mb-1 block text-xs font-medium text-n-600">Categoria</label>
          <select
            value={categoria}
            onChange={(e) => setCategoria(e.target.value)}
            className="w-full rounded-lg border border-n-200 bg-white px-3 py-2 text-sm"
          >
            <option value="utility">Utility — aviso operacional (mais barato)</option>
            <option value="marketing">Marketing — divulgação (mais caro, tem opt-out)</option>
          </select>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-n-600">Corpo</label>
          <Textarea
            value={corpo}
            onChange={(e) => setCorpo(e.target.value)}
            rows={4}
            placeholder="Olá, {{1}}! A escola {{2}} informa: {{3}} Em caso de dúvida, fale com a secretaria."
          />
          <p className="mt-1 text-[11px] text-n-400">
            Use {"{{1}}"}, {"{{2}}"}… para o que muda a cada envio. Não pode começar nem
            terminar com variável.
          </p>
          {problema && <p className="mt-1 text-[11px] text-danger">{problema}</p>}
        </div>

        {placeholders.length > 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-xs font-medium text-n-600">
              Exemplos (obrigatórios pela Meta — vão só para a revisão)
            </p>
            {placeholders.map((n, i) => (
              <Input
                key={n}
                value={exemplos[i] ?? ""}
                onChange={(e) => {
                  const copia = [...exemplos];
                  copia[i] = e.target.value;
                  setExemplos(copia);
                }}
                placeholder={`Exemplo para {{${n}}}`}
              />
            ))}
          </div>
        )}

        {corpo.trim() && !problema && (
          <div className="rounded-lg bg-n-50 p-3">
            <p className="mb-1 text-[11px] font-medium text-n-500">
              Como o responsável vai ver
            </p>
            <p className="whitespace-pre-wrap text-sm text-n-700">{previa}</p>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" variant="ghost" onClick={onFechar}>
            Cancelar
          </Button>
          <Button type="submit" size="sm" disabled={!podeEnviar}>
            {enviando ? "Enviando à Meta…" : "Enviar para aprovação"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
