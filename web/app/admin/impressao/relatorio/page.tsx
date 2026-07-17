"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  CotaImpressao,
  definirCotaImpressao,
  getSessao,
  listarCotasImpressao,
  listarProfessores,
  logout,
  Professor,
  RelatorioImpressao,
  relatorioImpressao,
  removerCotaImpressao,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/form";
import { TableWrap, Table, Th, Td, Tr } from "@/components/ui/Table";
import { Badge } from "@/components/ui/Badge";
import { useToast } from "@/components/ui/Toast";

function competenciaAtual(): string {
  return new Date().toISOString().slice(0, 7); // YYYY-MM
}

export default function RelatorioImpressaoPage() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [professores, setProfessores] = useState<Professor[]>([]);
  const [cotas, setCotas] = useState<CotaImpressao[]>([]);
  const [competencia, setCompetencia] = useState(competenciaAtual());
  const [relatorio, setRelatorio] = useState<RelatorioImpressao | null>(null);
  const toast = useToast();

  const recarregar = useCallback(async () => {
    const [profs, cts, rel] = await Promise.all([
      listarProfessores(),
      listarCotasImpressao(),
      relatorioImpressao(competencia),
    ]);
    setProfessores(profs);
    setCotas(cts);
    setRelatorio(rel);
  }, [competencia]);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    recarregar().catch(() =>
      toast({ tone: "danger", title: "Falha ao carregar o relatório." })
    );
  }, [router, recarregar, toast]);

  if (!usuario) return null;

  return (
    <AppShell
      title="Cotas & relatório de impressão"
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
      <div className="flex flex-col gap-[18px]">
        <CotasProfessores
          professores={professores}
          cotas={cotas}
          onMudou={recarregar}
        />

        <Card>
          <CardHeader
            title="Relatório mensal"
            action={
              <Input
                type="month"
                className="w-44"
                value={competencia}
                onChange={(e) => setCompetencia(e.target.value)}
              />
            }
          />
          {!relatorio || relatorio.linhas.length === 0 ? (
            <p className="text-sm text-n-500">
              Nenhum consumo ou cota nesta competência.
            </p>
          ) : (
            <>
              <p className="mb-3 text-sm text-n-600">
                Total do mês: <b>{relatorio.total_copias}</b> cópia(s) em{" "}
                <b>{relatorio.total_solicitacoes}</b> solicitação(ões).
              </p>
              <TableWrap>
                <Table>
                  <thead>
                    <tr>
                      <Th>Professor</Th>
                      <Th className="text-right">Solicitações</Th>
                      <Th className="text-right">Cópias</Th>
                      <Th className="text-right">Franquia</Th>
                      <Th>Situação</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {relatorio.linhas.map((linha) => (
                      <Tr key={linha.professor_id ?? linha.professor_nome}>
                        <Td className="font-medium">{linha.professor_nome}</Td>
                        <Td className="text-right">{linha.total_solicitacoes}</Td>
                        <Td className="text-right">{linha.total_copias}</Td>
                        <Td className="text-right text-n-600">
                          {linha.ilimitado ? "—" : linha.limite_mensal}
                        </Td>
                        <Td>
                          {linha.ilimitado ? (
                            <Badge tone="neutral">Sem limite</Badge>
                          ) : linha.excedeu ? (
                            <Badge tone="danger">Excedeu a franquia</Badge>
                          ) : (
                            <Badge tone="success">
                              Restam {linha.restante}
                            </Badge>
                          )}
                        </Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              </TableWrap>
            </>
          )}
        </Card>
      </div>
    </AppShell>
  );
}

function CotasProfessores({
  professores,
  cotas,
  onMudou,
}: {
  professores: Professor[];
  cotas: CotaImpressao[];
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [professorId, setProfessorId] = useState("");
  const [limite, setLimite] = useState(3000);

  const cotaPorProfessor = new Map(cotas.map((c) => [c.professor_id, c]));

  async function definir(e: React.FormEvent) {
    e.preventDefault();
    if (!professorId) return;
    try {
      await definirCotaImpressao(professorId, limite);
      setProfessorId("");
      setLimite(3000);
      await onMudou();
      toast({ tone: "success", title: "Franquia definida." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha." });
    }
  }

  async function remover(pid: string) {
    try {
      await removerCotaImpressao(pid);
      await onMudou();
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha." });
    }
  }

  return (
    <Card>
      <CardHeader title="Franquia mensal por professor" />
      <p className="mb-3 text-sm text-n-500">
        Defina a cota de cópias/mês por professor (0 = sem limite). O relatório abaixo
        sinaliza quem bateu a meta.
      </p>
      <form onSubmit={definir} className="mb-3 flex flex-wrap items-center gap-2">
        <Select
          className="w-56"
          value={professorId}
          onChange={(e) => setProfessorId(e.target.value)}
        >
          <option value="">— Professor —</option>
          {professores.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nome}
            </option>
          ))}
        </Select>
        <Input
          className="w-32"
          type="number"
          min={0}
          value={limite}
          onChange={(e) => setLimite(Number(e.target.value))}
          placeholder="Cópias/mês"
        />
        <Button size="sm" type="submit">
          Definir franquia
        </Button>
      </form>

      {professores.length === 0 ? (
        <p className="text-sm text-n-500">Cadastre professores para definir cotas.</p>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Professor</Th>
                <Th className="text-right">Franquia mensal</Th>
                <Th className="text-right">Ações</Th>
              </tr>
            </thead>
            <tbody>
              {professores.map((p) => {
                const cota = cotaPorProfessor.get(p.id);
                return (
                  <Tr key={p.id}>
                    <Td className="font-medium">{p.nome}</Td>
                    <Td className="text-right text-n-600">
                      {!cota || cota.ilimitado
                        ? "Sem limite"
                        : `${cota.limite_mensal} cópias`}
                    </Td>
                    <Td className="text-right">
                      {cota && !cota.ilimitado && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => remover(p.id)}
                        >
                          Remover franquia
                        </Button>
                      )}
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
        </TableWrap>
      )}
    </Card>
  );
}
