"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  confirmarLeitura,
  getSessaoProfessor,
  logoutProfessor,
  meusRecados,
  ProfessorLogado,
  RecadoDoProfessor,
  solicitarImpressaoProfessor,
} from "@/lib/professor";

import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/form";
import { Badge } from "@/components/ui/Badge";
import { useToast } from "@/components/ui/Toast";
import { CheckIcon, PrintIcon } from "@/components/ui/icons";

export default function PortalProfessor() {
  const router = useRouter();
  const toast = useToast();
  const [professor, setProfessor] = useState<ProfessorLogado | null>(null);
  const [recados, setRecados] = useState<RecadoDoProfessor[]>([]);

  const recarregar = useCallback(async () => {
    setRecados(await meusRecados());
  }, []);

  useEffect(() => {
    const s = getSessaoProfessor();
    if (!s) {
      router.replace("/professor/login");
      return;
    }
    setProfessor(s.professor);
    recarregar().catch(() => toast({ tone: "danger", title: "Falha ao carregar recados." }));
  }, [router, recarregar, toast]);

  async function confirmar(id: string) {
    try {
      await confirmarLeitura(id);
      await recarregar();
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao confirmar." });
    }
  }

  if (!professor) return null;

  const pendentes = recados.filter((r) => !r.lido).length;

  return (
    <div className="min-h-screen bg-n-50">
      <header className="flex items-center justify-between border-b border-n-100 bg-white px-4 py-3">
        <div>
          <div className="text-sm font-extrabold tracking-tight text-n-900">
            TI<span className="text-brand-600">·</span>Escolar
          </div>
          <div className="text-xs text-n-500">Mural · {professor.nome}</div>
        </div>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => {
            logoutProfessor();
            router.replace("/professor/login");
          }}
        >
          Sair
        </Button>
      </header>

      <main className="mx-auto flex max-w-2xl flex-col gap-4 p-4">
        <Card>
          <CardHeader
            title="Recados da secretaria"
            action={
              pendentes > 0 ? (
                <Badge tone="warning">{pendentes} não lido(s)</Badge>
              ) : (
                <Badge tone="success" dot>
                  Tudo em dia
                </Badge>
              )
            }
          />
          {recados.length === 0 ? (
            <p className="text-sm text-n-500">Nenhum recado no momento.</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {recados.map((r) => (
                <li
                  key={r.id}
                  className={`rounded-xl border p-3 ${
                    r.lido ? "border-n-100 bg-white" : "border-brand-200 bg-brand-50"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-bold text-n-900">{r.titulo}</div>
                      <div className="mt-0.5 text-xs text-n-400">
                        {r.autor_nome || "Secretaria"} ·{" "}
                        {new Date(r.criado_em).toLocaleString("pt-BR")}
                      </div>
                    </div>
                    {r.lido ? (
                      <Badge tone="success" dot>
                        Lido
                      </Badge>
                    ) : (
                      <Button
                        size="sm"
                        leftIcon={<CheckIcon size={14} />}
                        onClick={() => confirmar(r.id)}
                      >
                        Confirmar leitura
                      </Button>
                    )}
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm text-n-700">{r.corpo}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <SolicitarImpressao />
      </main>
    </div>
  );
}

function SolicitarImpressao() {
  const toast = useToast();
  const [arquivo, setArquivo] = useState("");
  const [copias, setCopias] = useState(1);
  const [colorido, setColorido] = useState(false);
  const [frenteVerso, setFrenteVerso] = useState(false);
  const [observacao, setObservacao] = useState("");

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (!arquivo.trim() || copias < 1) return;
    try {
      await solicitarImpressaoProfessor({
        arquivo_nome: arquivo.trim(),
        copias,
        colorido,
        frente_verso: frenteVerso,
        observacao: observacao.trim(),
      });
      setArquivo("");
      setCopias(1);
      setColorido(false);
      setFrenteVerso(false);
      setObservacao("");
      toast({ tone: "success", title: "Enviado para a fila de impressão da secretaria." });
    } catch (err) {
      toast({ tone: "danger", title: err instanceof Error ? err.message : "Falha ao enviar." });
    }
  }

  return (
    <Card>
      <CardHeader title="Solicitar impressão" />
      <p className="mb-3 text-xs text-n-400">
        Informe o arquivo e os parâmetros. O pedido cai na fila da secretaria.
      </p>
      <form onSubmit={enviar} className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          <Input
            className="flex-1 min-w-[180px]"
            value={arquivo}
            onChange={(e) => setArquivo(e.target.value)}
            placeholder="Nome do arquivo, ex.: prova_5A.pdf"
          />
          <Input
            className="w-24"
            type="number"
            min={1}
            value={copias}
            onChange={(e) => setCopias(Number(e.target.value))}
          />
        </div>
        <div className="flex flex-wrap items-center gap-4 text-sm text-n-600">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={colorido} onChange={(e) => setColorido(e.target.checked)} />
            Colorido
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={frenteVerso}
              onChange={(e) => setFrenteVerso(e.target.checked)}
            />
            Frente e verso
          </label>
        </div>
        <Input
          value={observacao}
          onChange={(e) => setObservacao(e.target.value)}
          placeholder="Observação (opcional)"
        />
        <div>
          <Button size="sm" type="submit" leftIcon={<PrintIcon size={15} />}>
            Enviar para impressão
          </Button>
        </div>
      </form>
    </Card>
  );
}
