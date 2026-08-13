"use client";

/**
 * Busca instantânea de aluno (§4.1 do plano de 10/08).
 *
 * Substitui o `<select>` que carregava **200 alunos** de uma vez: a partir do aluno 201
 * não havia como vincular um documento. Era um bug de dados disfarçado de UX — uma escola
 * de porte médio já estoura esse teto, e o problema aparece justamente no aluno que
 * ninguém procurou ainda.
 *
 * Busca no servidor com debounce, teto de 20 resultados. Só alunos **ativos**: vincular um
 * atestado a um ex-aluno é quase sempre engano.
 */

import { useEffect, useRef, useState } from "react";
import { Aluno, listarAlunos } from "@/lib/admin";
import { Input } from "@/components/ui/form";
import { cn } from "@/components/ui/cn";

/** Tempo de digitação parada antes de consultar. Curto o bastante para não travar. */
const DEBOUNCE_MS = 250;
const MAX_RESULTADOS = 20;

export function BuscaAluno({
  alunoId,
  alunoNome,
  onSelecionar,
  placeholder = "Buscar aluno por nome ou matrícula…",
}: {
  alunoId: string | null;
  alunoNome: string;
  /** `null` desvincula. */
  onSelecionar: (alunoId: string | null, nome: string) => void;
  placeholder?: string;
}) {
  const [termo, setTermo] = useState("");
  const [resultados, setResultados] = useState<Aluno[]>([]);
  const [aberto, setAberto] = useState(false);
  const [buscando, setBuscando] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => {
      if (caixa.current && !caixa.current.contains(e.target as Node)) setAberto(false);
    };
    document.addEventListener("mousedown", fora);
    return () => document.removeEventListener("mousedown", fora);
  }, [aberto]);

  useEffect(() => {
    const busca = termo.trim();
    if (busca.length < 2) {
      // Uma letra traria meia escola e não ajuda ninguém.
      setResultados([]);
      return;
    }
    let vivo = true;
    setBuscando(true);
    const timer = setTimeout(() => {
      listarAlunos(undefined, true, 1, MAX_RESULTADOS, busca)
        .then((p) => vivo && setResultados(p.itens))
        .catch(() => vivo && setResultados([]))
        .finally(() => vivo && setBuscando(false));
    }, DEBOUNCE_MS);
    return () => {
      vivo = false;
      clearTimeout(timer);
    };
  }, [termo]);

  if (alunoId) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-n-200 bg-n-50 px-3 py-1.5">
        <span className="text-[13px] font-medium text-n-800">{alunoNome || "Aluno"}</span>
        <button
          type="button"
          onClick={() => onSelecionar(null, "")}
          className="text-xs font-semibold text-danger hover:underline"
        >
          Desvincular
        </button>
      </div>
    );
  }

  return (
    <div className="relative w-64" ref={caixa}>
      <Input
        value={termo}
        onChange={(e) => {
          setTermo(e.target.value);
          setAberto(true);
        }}
        onFocus={() => setAberto(true)}
        placeholder={placeholder}
      />
      {aberto && termo.trim().length >= 2 && (
        <div className="absolute z-30 mt-1 max-h-[240px] w-full overflow-y-auto rounded-xl border border-n-200 bg-white p-1 shadow-lg">
          {resultados.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => {
                onSelecionar(a.id, a.nome);
                setTermo("");
                setAberto(false);
              }}
              className={cn(
                "block w-full rounded-lg px-2.5 py-1.5 text-left text-[13px]",
                "text-n-700 hover:bg-n-50",
              )}
            >
              {a.nome}
              <span className="ml-1.5 text-[11px] text-n-400">
                {[a.sala_nome, a.matricula].filter(Boolean).join(" · ")}
              </span>
            </button>
          ))}
          {resultados.length === 0 && (
            <p className="px-2.5 py-2 text-[12.5px] text-n-400">
              {buscando ? "Buscando…" : "Nenhum aluno encontrado."}
            </p>
          )}
          {resultados.length === MAX_RESULTADOS && (
            <p className="px-2.5 py-1.5 text-[11px] text-n-400">
              Mostrando os {MAX_RESULTADOS} primeiros — refine a busca.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
