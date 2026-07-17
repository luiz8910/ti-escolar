"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  getSessao,
  inativarResponsaveis,
  listarSalas,
  logout,
  promoverTurmas,
  ResponsavelInativado,
  ResultadoPromocao,
  Sala,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/form";
import { TableWrap, Table, Th, Td, Tr } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

const FORMAR = "__formar__"; // destino "última série": marca ex-alunos

export default function ProgressaoPage() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [salas, setSalas] = useState<Sala[]>([]);
  const [destinos, setDestinos] = useState<Record<string, string>>({});
  const [resultados, setResultados] = useState<ResultadoPromocao[]>([]);
  const [inativados, setInativados] = useState<ResponsavelInativado[] | null>(null);
  const toast = useToast();

  const recarregar = useCallback(async () => {
    setSalas(await listarSalas());
  }, []);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    setUsuario(s.usuario);
    recarregar().catch(() =>
      toast({ tone: "danger", title: "Falha ao carregar as séries." })
    );
  }, [router, recarregar, toast]);

  async function promover() {
    const promocoes = Object.entries(destinos)
      .filter(([, destino]) => destino)
      .map(([origem, destino]) => ({
        origem_sala_id: origem,
        destino_sala_id: destino === FORMAR ? null : destino,
      }));
    if (promocoes.length === 0) {
      toast({ tone: "danger", title: "Escolha ao menos um destino." });
      return;
    }
    try {
      const res = await promoverTurmas(promocoes);
      setResultados(res);
      setDestinos({});
      await recarregar();
      toast({ tone: "success", title: "Promoção concluída." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha." });
    }
  }

  async function inativar() {
    try {
      const res = await inativarResponsaveis();
      setInativados(res);
      toast({
        tone: "success",
        title: `${res.length} responsável(is) inativado(s).`,
      });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha." });
    }
  }

  if (!usuario) return null;

  return (
    <AppShell
      title="Progressão de série"
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
        <Card>
          <CardHeader title="Virada de ano — promover turmas" />
          <p className="mb-3 text-sm text-n-500">
            Para cada série, escolha a série seguinte (ou “Formar” na última série, que
            marca os alunos como ex-alunos). Só alunos ativos são promovidos.
          </p>
          {salas.length === 0 ? (
            <p className="text-sm text-n-500">Cadastre séries para promover.</p>
          ) : (
            <>
              <TableWrap>
                <Table>
                  <thead>
                    <tr>
                      <Th>Série de origem</Th>
                      <Th>Destino</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {salas.map((sala) => (
                      <Tr key={sala.id}>
                        <Td className="font-medium">{sala.nome}</Td>
                        <Td>
                          <Select
                            className="w-64"
                            value={destinos[sala.id] ?? ""}
                            onChange={(e) =>
                              setDestinos((d) => ({ ...d, [sala.id]: e.target.value }))
                            }
                          >
                            <option value="">— Não promover —</option>
                            <option value={FORMAR}>Formar (última série)</option>
                            {salas
                              .filter((s) => s.id !== sala.id)
                              .map((s) => (
                                <option key={s.id} value={s.id}>
                                  {s.nome}
                                </option>
                              ))}
                          </Select>
                        </Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              </TableWrap>
              <div className="mt-3">
                <Button size="sm" onClick={promover}>
                  Promover turmas selecionadas
                </Button>
              </div>
            </>
          )}

          {resultados.length > 0 && (
            <div className="mt-4 rounded-[10px] bg-n-50 p-3 text-sm text-n-700">
              <div className="mb-1 font-bold text-n-600">Resultado</div>
              <ul className="list-disc pl-5">
                {resultados.map((r) => (
                  <li key={r.origem_sala_id}>
                    {r.origem_sala_nome}:{" "}
                    {r.destino_sala_id
                      ? `${r.alunos_promovidos} promovido(s) → ${r.destino_sala_nome}`
                      : `${r.alunos_formados} formado(s) (ex-aluno)`}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="Ciclo de vida do responsável" />
          <p className="mb-3 text-sm text-n-500">
            Inativa os responsáveis cujos alunos já são <b>todos</b> ex-alunos —
            eliminando o retrabalho de desfazer contato a contato. Não mexe em quem ainda
            tem algum aluno ativo.
          </p>
          <Button size="sm" variant="secondary" onClick={inativar}>
            Inativar responsáveis sem alunos ativos
          </Button>

          {inativados && (
            <div className="mt-3 text-sm text-n-700">
              {inativados.length === 0 ? (
                <p className="text-n-500">
                  Nenhum responsável para inativar — todos têm ao menos um aluno ativo.
                </p>
              ) : (
                <ul className="list-disc pl-5">
                  {inativados.map((r) => (
                    <li key={r.contato_id}>
                      {r.nome} · {r.telefone}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </Card>
      </div>
    </AppShell>
  );
}
