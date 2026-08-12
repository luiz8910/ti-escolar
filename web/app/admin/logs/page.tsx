"use client";

/**
 * Painel de Logs — observabilidade operacional (super admin).
 *
 * Inspirado no Laravel Horizon: primeiro o estado agregado da janela recente (é ou não é
 * saudável agora), depois a fila de atendimentos do WhatsApp, e só então o log linha a
 * linha para investigar. A ordem é essa de propósito — quem abre esta tela normalmente
 * quer saber "está tudo bem?" antes de "o que aconteceu às 14h07?".
 *
 * Exclusivo do super admin: o log é cross-tenant e carrega detalhe de infraestrutura
 * (traceback, rota, id interno) que não é material para a secretaria. O que a escola
 * precisa ver do próprio funcionamento está em HISTÓRICO.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  AtendimentoInbound,
  getSessao,
  listarAtendimentosInbound,
  listarLogs,
  LogsPagina,
  logout,
  NivelLog,
  obterResumoLogs,
  RegistroLog,
  ResumoLogs,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input, Select } from "@/components/ui/form";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/components/ui/cn";
import { AlertIcon, CheckIcon, FileIcon } from "@/components/ui/icons";

const NIVEIS: Record<NivelLog, { rotulo: string; tone: "success" | "warning" | "danger" | "neutral" }> = {
  INFO: { rotulo: "Info", tone: "neutral" },
  WARNING: { rotulo: "Alerta", tone: "warning" },
  ERROR: { rotulo: "Erro", tone: "danger" },
  CRITICAL: { rotulo: "Crítico", tone: "danger" },
};

const STATUS_ATENDIMENTO: Record<string, { rotulo: string; tone: "success" | "warning" | "danger" }> = {
  concluida: { rotulo: "Respondida", tone: "success" },
  em_atendimento: { rotulo: "Em atendimento", tone: "warning" },
  falhou: { rotulo: "Falhou", tone: "danger" },
};

// Opções de itens por página — o usuário escolhe, o padrão é o menor (item 7).
const TAMANHOS = [10, 25, 50, 100];
const JANELAS = [
  { valor: 1, rotulo: "última hora" },
  { valor: 24, rotulo: "últimas 24h" },
  { valor: 168, rotulo: "últimos 7 dias" },
];

function hora(data: string): string {
  return new Date(data).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function Tile({
  rotulo,
  valor,
  sufixo = "",
  tone = "neutral",
}: {
  rotulo: string;
  valor: number | string;
  sufixo?: string;
  tone?: "success" | "warning" | "danger" | "neutral";
}) {
  const cor =
    tone === "danger"
      ? "text-danger"
      : tone === "warning"
        ? "text-accent"
        : tone === "success"
          ? "text-success"
          : "text-n-900";
  return (
    <Card className="flex flex-col justify-center gap-1 py-3.5">
      <span className="text-[10.5px] font-bold uppercase tracking-[0.08em] text-n-400">
        {rotulo}
      </span>
      <span className={cn("text-[19px] font-extrabold leading-none", cor)}>
        {valor}
        {sufixo && <span className="ml-0.5 text-[12px] font-semibold text-n-400">{sufixo}</span>}
      </span>
    </Card>
  );
}

export default function LogsPage() {
  const router = useRouter();
  const toast = useToast();
  const [usuario, setUsuario] = useState<Usuario | null>(null);

  const [resumo, setResumo] = useState<ResumoLogs | null>(null);
  const [pagina, setPagina] = useState<LogsPagina | null>(null);
  const [atendimentos, setAtendimentos] = useState<AtendimentoInbound[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [expandido, setExpandido] = useState<string | null>(null);

  // Filtros
  const [janela, setJanela] = useState(24);
  const [nivel, setNivel] = useState("");
  const [loggerNome, setLoggerNome] = useState("");
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [numPagina, setNumPagina] = useState(1);
  const [porPagina, setPorPagina] = useState(10);
  const [autoAtualizar, setAutoAtualizar] = useState(false);

  const carregar = useCallback(async () => {
    const [r, p, a] = await Promise.all([
      obterResumoLogs(janela),
      listarLogs({
        nivel,
        logger_nome: loggerNome,
        busca: buscaAplicada,
        pagina: numPagina,
        por_pagina: porPagina,
      }),
      listarAtendimentosInbound("", 10),
    ]);
    setResumo(r);
    setPagina(p);
    setAtendimentos(a);
  }, [janela, nivel, loggerNome, buscaAplicada, numPagina, porPagina]);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    // Log é material de operação da plataforma, não da escola.
    if (s.usuario.papel !== "super_admin") {
      router.replace("/admin");
      return;
    }
    setUsuario(s.usuario);
  }, [router]);

  useEffect(() => {
    if (!usuario) return;
    setCarregando(true);
    carregar()
      .catch(() => toast({ tone: "danger", title: "Falha ao carregar os logs." }))
      .finally(() => setCarregando(false));
  }, [usuario, carregar, toast]);

  // Atualização periódica opcional: útil enquanto se acompanha um incidente, mas
  // desligada por padrão para não ficar batendo no banco com a aba esquecida aberta.
  useEffect(() => {
    if (!autoAtualizar || !usuario) return;
    const id = setInterval(() => {
      carregar().catch(() => undefined);
    }, 10_000);
    return () => clearInterval(id);
  }, [autoAtualizar, usuario, carregar]);

  function sair() {
    logout();
    router.replace("/admin/login");
  }

  function aplicarBusca(e: React.FormEvent) {
    e.preventDefault();
    setNumPagina(1);
    setBuscaAplicada(busca.trim());
  }

  if (!usuario) return null;

  const meta = pagina?.meta;

  return (
    <AppShell
      exigeEscola={false}
      title="Logs"
      user={{ name: usuario.nome, role: "Super Admin" }}
      isSuperAdmin
      onLogout={sair}
    >
      <div className="flex flex-col gap-[18px]">
        <div className="flex flex-wrap items-center gap-3">
          <Select
            value={janela}
            onChange={(e) => {
              setJanela(Number(e.target.value));
              setNumPagina(1);
            }}
            className="w-auto"
          >
            {JANELAS.map((j) => (
              <option key={j.valor} value={j.valor}>
                Resumo das {j.rotulo}
              </option>
            ))}
          </Select>
          <label className="flex items-center gap-2 text-[12.5px] font-semibold text-n-600">
            <input
              type="checkbox"
              checked={autoAtualizar}
              onChange={(e) => setAutoAtualizar(e.target.checked)}
              className="h-3.5 w-3.5 accent-brand-600"
            />
            Atualizar a cada 10s
          </label>
          <Button
            variant="secondary"
            onClick={() => carregar().catch(() => undefined)}
            className="ml-auto"
          >
            Atualizar agora
          </Button>
        </div>

        {/* Estado agregado — "está tudo bem agora?" */}
        {resumo && (
          <>
            <div
              className={cn(
                "flex items-start gap-3 rounded-lg border px-4 py-3.5 text-[13px]",
                resumo.saudavel
                  ? "border-success/30 bg-success/5 text-n-800"
                  : "border-danger/30 bg-danger/5 text-n-800",
              )}
            >
              {resumo.saudavel ? (
                <CheckIcon size={18} className="mt-0.5 flex-none text-success" />
              ) : (
                <AlertIcon size={18} className="mt-0.5 flex-none text-danger" />
              )}
              <p>
                {resumo.saudavel ? (
                  <>
                    Nenhum erro e nenhum atendimento travado nas últimas{" "}
                    {resumo.janela_horas}h.
                  </>
                ) : (
                  <>
                    <b>{resumo.erros}</b> erro(s) e <b>{resumo.atendimentos_falhos}</b>{" "}
                    atendimento(s) do WhatsApp sem resposta nas últimas {resumo.janela_horas}h.
                    Um atendimento falho significa que um responsável escreveu e{" "}
                    <b>não foi respondido</b>.
                  </>
                )}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
              <Tile rotulo="Erros" valor={resumo.erros} tone={resumo.erros ? "danger" : "success"} />
              <Tile
                rotulo="Alertas"
                valor={resumo.alertas}
                tone={resumo.alertas ? "warning" : "neutral"}
              />
              <Tile rotulo="Requisições" valor={resumo.requisicoes} />
              <Tile rotulo="Taxa de erro" valor={resumo.taxa_erro_percentual} sufixo="%" />
              <Tile rotulo="Latência média" valor={resumo.duracao_media_ms} sufixo="ms" />
              <Tile rotulo="p95" valor={resumo.duracao_p95_ms} sufixo="ms" />
            </div>
          </>
        )}

        {/* Fila de atendimentos — o análogo das filas do Horizon */}
        <Card className="p-0">
          <div className="flex items-center justify-between border-b border-n-100 px-4 py-3">
            <div>
              <h2 className="text-[13.5px] font-bold text-n-900">Atendimentos do WhatsApp</h2>
              <p className="mt-0.5 text-[11.5px] text-n-500">
                Cada mensagem recebida e em que pé ficou. &quot;Em atendimento&quot; por muito
                tempo indica processo derrubado no meio.
              </p>
            </div>
            {resumo && (
              <div className="flex gap-2">
                <Badge tone="success">{resumo.atendimentos_concluidos} respondidas</Badge>
                <Badge tone="warning">{resumo.atendimentos_em_andamento} em curso</Badge>
                <Badge tone="danger">{resumo.atendimentos_falhos} falhas</Badge>
              </div>
            )}
          </div>
          {atendimentos.length === 0 ? (
            <div className="px-4 py-6">
              <EmptyState
                icon={<FileIcon size={22} />}
                title="Nenhum atendimento registrado"
                description="Assim que uma mensagem chegar pelo webhook da Meta, ela aparece aqui."
              />
            </div>
          ) : (
            <TableWrap>
              <Table>
                <thead>
                  <Tr>
                    <Th>Situação</Th>
                    <Th>Responsável</Th>
                    <Th>Escola</Th>
                    <Th>Resposta / motivo</Th>
                    <Th>Atualizado</Th>
                  </Tr>
                </thead>
                <tbody>
                  {atendimentos.map((a) => {
                    const s = STATUS_ATENDIMENTO[a.status] ?? {
                      rotulo: a.status,
                      tone: "warning" as const,
                    };
                    return (
                      <Tr key={a.chave}>
                        <Td>
                          <Badge tone={s.tone}>{s.rotulo}</Badge>
                        </Td>
                        <Td className="font-mono text-[12px]">{a.origem || "—"}</Td>
                        <Td>{a.tenant_nome || "—"}</Td>
                        <Td className="max-w-[320px] truncate text-n-600">{a.resumo || "—"}</Td>
                        <Td className="whitespace-nowrap text-n-500">{hora(a.atualizado_em)}</Td>
                      </Tr>
                    );
                  })}
                </tbody>
              </Table>
            </TableWrap>
          )}
        </Card>

        {/* Log linha a linha */}
        <Card className="p-0">
          <div className="border-b border-n-100 px-4 py-3">
            <h2 className="text-[13.5px] font-bold text-n-900">Registros</h2>
            <form onSubmit={aplicarBusca} className="mt-3 flex flex-wrap items-end gap-2">
              <Select
                value={nivel}
                onChange={(e) => {
                  setNivel(e.target.value);
                  setNumPagina(1);
                }}
                className="w-auto"
              >
                <option value="">Todos os níveis</option>
                {(Object.keys(NIVEIS) as NivelLog[]).map((n) => (
                  <option key={n} value={n}>
                    {NIVEIS[n].rotulo}
                  </option>
                ))}
              </Select>
              <Select
                value={loggerNome}
                onChange={(e) => {
                  setLoggerNome(e.target.value);
                  setNumPagina(1);
                }}
                className="w-auto"
              >
                <option value="">Toda a aplicação</option>
                {(pagina?.loggers ?? []).map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </Select>
              <Input
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                placeholder="Buscar na mensagem…"
                className="w-[220px]"
              />
              <Button type="submit" variant="secondary">
                Filtrar
              </Button>
              <div className="ml-auto flex items-center gap-2 text-[12px] font-semibold text-n-500">
                Itens por página
                <Select
                  value={porPagina}
                  onChange={(e) => {
                    setPorPagina(Number(e.target.value));
                    setNumPagina(1);
                  }}
                  className="w-auto"
                >
                  {TAMANHOS.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </Select>
              </div>
            </form>
          </div>

          {carregando ? (
            <p className="px-4 py-6 text-sm text-n-400">Carregando…</p>
          ) : !pagina || pagina.itens.length === 0 ? (
            <div className="px-4 py-6">
              <EmptyState
                icon={<FileIcon size={22} />}
                title="Nenhum registro para este filtro"
                description="Ajuste o nível, o módulo ou o termo buscado."
              />
            </div>
          ) : (
            <>
              <TableWrap>
                <Table>
                  <thead>
                    <Tr>
                      <Th>Quando</Th>
                      <Th>Nível</Th>
                      <Th>Módulo</Th>
                      <Th>Mensagem</Th>
                      <Th>Duração</Th>
                      <Th>Código</Th>
                    </Tr>
                  </thead>
                  <tbody>
                    {pagina.itens.map((r: RegistroLog) => {
                      const n = NIVEIS[r.nivel] ?? NIVEIS.INFO;
                      const aberto = expandido === r.id;
                      return (
                        <Tr
                          key={r.id}
                          className={cn(r.excecao && "cursor-pointer")}
                          onClick={() => r.excecao && setExpandido(aberto ? null : r.id)}
                        >
                          <Td className="whitespace-nowrap text-n-500">{hora(r.criado_em)}</Td>
                          <Td>
                            <Badge tone={n.tone}>{n.rotulo}</Badge>
                          </Td>
                          <Td className="font-mono text-[11.5px] text-n-600">{r.logger}</Td>
                          <Td className="max-w-[420px]">
                            <div className="truncate text-n-800">{r.mensagem}</div>
                            {aberto && r.excecao && (
                              <pre className="mt-2 max-h-[260px] overflow-auto rounded-md bg-n-900 p-3 text-[11px] leading-relaxed text-n-100">
                                {r.excecao}
                              </pre>
                            )}
                            {r.excecao && !aberto && (
                              <span className="text-[11px] font-semibold text-brand-600">
                                clique para ver o traceback
                              </span>
                            )}
                          </Td>
                          <Td className="whitespace-nowrap text-n-500">
                            {r.duracao_ms != null ? `${r.duracao_ms}ms` : "—"}
                          </Td>
                          <Td className="whitespace-nowrap font-mono text-[11px] text-n-500">
                            {r.correlacao_id || "—"}
                          </Td>
                        </Tr>
                      );
                    })}
                  </tbody>
                </Table>
              </TableWrap>

              {meta && (
                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-n-100 px-4 py-3 text-[12.5px] text-n-500">
                  <span>
                    {meta.total} registro(s) · página {meta.pagina} de {meta.total_paginas}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      disabled={meta.pagina <= 1}
                      onClick={() => setNumPagina((p) => Math.max(1, p - 1))}
                    >
                      Anterior
                    </Button>
                    <Button
                      variant="secondary"
                      disabled={meta.pagina >= meta.total_paginas}
                      onClick={() => setNumPagina((p) => p + 1)}
                    >
                      Próxima
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </Card>

        {/* Rankings do resumo */}
        {resumo && (resumo.rotas_mais_lentas.length > 0 || resumo.erros_mais_comuns.length > 0) && (
          <div className="grid gap-3 lg:grid-cols-2">
            <Card>
              <h3 className="mb-2 text-[13px] font-bold text-n-900">Rotas mais lentas</h3>
              {resumo.rotas_mais_lentas.length === 0 ? (
                <p className="text-[12.5px] text-n-400">Sem dados na janela.</p>
              ) : (
                <ul className="flex flex-col gap-1.5">
                  {resumo.rotas_mais_lentas.map((c) => (
                    <li key={c.rotulo} className="flex justify-between gap-3 text-[12.5px]">
                      <span className="truncate font-mono text-n-600">{c.rotulo}</span>
                      <span className="flex-none font-semibold text-n-900">{c.quantidade}ms</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <h3 className="mb-2 text-[13px] font-bold text-n-900">Erros mais frequentes</h3>
              {resumo.erros_mais_comuns.length === 0 ? (
                <p className="text-[12.5px] text-n-400">Nenhum erro na janela.</p>
              ) : (
                <ul className="flex flex-col gap-1.5">
                  {resumo.erros_mais_comuns.map((c) => (
                    <li key={c.rotulo} className="flex justify-between gap-3 text-[12.5px]">
                      <span className="truncate text-n-600">{c.rotulo}</span>
                      <span className="flex-none font-semibold text-danger">{c.quantidade}×</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        )}
      </div>
    </AppShell>
  );
}
