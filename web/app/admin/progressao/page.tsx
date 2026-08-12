"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  exigeEscolhaDeEscola,
  getSessao,
  sincronizarResponsaveis,
  listarSalas,
  logout,
  promoverTurmas,
  ResponsavelInativado,
  SincronizacaoResponsaveis,
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
  const [sincronizacao, setSincronizacao] = useState<SincronizacaoResponsaveis | null>(
    null,
  );
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
    // Super admin sem escola escolhida: a AppShell mostra o pedido de escolha e
    // nenhuma busca é disparada — `tenantEmFoco()` lançaria, e antes desta guarda o
    // painel simplesmente operava sobre a escola de demonstração.
    if (exigeEscolhaDeEscola()) return;
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

  async function sincronizar() {
    try {
      const res = await sincronizarResponsaveis();
      setSincronizacao(res);
      const total = res.inativados.length + res.reativados.length;
      toast({
        tone: "success",
        title: total
          ? `${res.inativados.length} inativado(s), ${res.reativados.length} reativado(s).`
          : "Tudo já estava em dia.",
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
          <div className="mb-3 flex items-start gap-3 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2.5 text-[12.5px] text-brand-900">
            <span>
              <b>Isto já acontece sozinho.</b> A situação do responsável é ajustada na
              promoção de turmas acima e sempre que um aluno é desativado ou rematriculado
              — quem fica sem nenhum aluno ativo sai, quem volta a ter aluno retorna.
            </span>
          </div>
          <p className="mb-3 text-sm text-n-500">
            O botão abaixo é um <b>reprocessamento</b> da escola inteira: use depois de uma
            importação em massa ou de um ajuste feito fora do painel, para conferir que não
            ficou ninguém para trás.
          </p>
          <Button size="sm" variant="secondary" onClick={sincronizar}>
            Reprocessar situação dos responsáveis
          </Button>

          {sincronizacao && (
            <div className="mt-3 flex flex-col gap-2 text-sm text-n-700">
              {sincronizacao.inativados.length === 0 &&
              sincronizacao.reativados.length === 0 ? (
                <p className="text-n-500">
                  Nada a ajustar — a situação de todos já estava correta.
                </p>
              ) : (
                <>
                  <ListaResponsaveis
                    titulo="Inativados (sem nenhum aluno ativo)"
                    itens={sincronizacao.inativados}
                  />
                  <ListaResponsaveis
                    titulo="Reativados (voltaram a ter aluno ativo)"
                    itens={sincronizacao.reativados}
                  />
                </>
              )}
            </div>
          )}
        </Card>
      </div>
    </AppShell>
  );
}

// --------------------------------------------------------------------------- //
/** Um lado da sincronização. Some quando não há nada — lista vazia é só ruído. */
function ListaResponsaveis({
  titulo,
  itens,
}: {
  titulo: string;
  itens: ResponsavelInativado[];
}) {
  if (itens.length === 0) return null;
  return (
    <div>
      <p className="text-[12.5px] font-bold text-n-800">
        {titulo} · {itens.length}
      </p>
      <ul className="list-disc pl-5">
        {itens.map((r) => (
          <li key={r.contato_id}>
            {r.nome} · {r.telefone}
          </li>
        ))}
      </ul>
    </div>
  );
}
