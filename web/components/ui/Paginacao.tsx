"use client";

/**
 * Paginador reutilizável (item 7).
 *
 * Um componente só para todas as listagens: a régua de "quantos itens por página" é uma
 * preferência do usuário, e ela precisa se comportar igual em Alunos, Conversas, Disparos
 * e Auditoria — do contrário cada tela vira um dialeto.
 *
 * A escolha de tamanho é **persistida** por tela (`localStorage`): quem trabalha com 100
 * por página não quer reconfigurar isso a cada visita.
 */

import { Select } from "./form";
import { Button } from "./Button";

export const TAMANHOS_DE_PAGINA = [10, 25, 50, 100];

export interface PaginaMeta {
  pagina: number;
  por_pagina: number;
  total: number;
  total_paginas: number;
}

/** Lê a preferência salva de itens por página. `escopo` separa uma tela da outra. */
export function tamanhoPreferido(escopo: string, padrao = 10): number {
  if (typeof window === "undefined") return padrao;
  const salvo = Number(window.localStorage.getItem(`paginacao:${escopo}`));
  return TAMANHOS_DE_PAGINA.includes(salvo) ? salvo : padrao;
}

export function salvarTamanhoPreferido(escopo: string, tamanho: number) {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(`paginacao:${escopo}`, String(tamanho));
  }
}

export function Paginacao({
  meta,
  onPagina,
  onTamanho,
  rotulo = "registro(s)",
}: {
  meta: PaginaMeta;
  onPagina: (pagina: number) => void;
  onTamanho: (tamanho: number) => void;
  /** Substantivo no plural para o contador ("aluno(s)", "conversa(s)"). */
  rotulo?: string;
}) {
  const primeiro = meta.total === 0 ? 0 : (meta.pagina - 1) * meta.por_pagina + 1;
  const ultimo = Math.min(meta.pagina * meta.por_pagina, meta.total);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-n-100 px-4 py-3 text-[12.5px] text-n-500">
      <span>
        {meta.total === 0
          ? `Nenhum ${rotulo.replace("(s)", "")}`
          : `${primeiro}–${ultimo} de ${meta.total} ${rotulo}`}
      </span>

      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 font-semibold">
          Por página
          <Select
            className="w-20"
            value={meta.por_pagina}
            onChange={(e) => onTamanho(Number(e.target.value))}
          >
            {TAMANHOS_DE_PAGINA.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
        </label>

        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={meta.pagina <= 1}
            onClick={() => onPagina(meta.pagina - 1)}
          >
            Anterior
          </Button>
          <span className="whitespace-nowrap font-semibold text-n-600">
            {meta.pagina} / {meta.total_paginas}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={meta.pagina >= meta.total_paginas}
            onClick={() => onPagina(meta.pagina + 1)}
          >
            Próxima
          </Button>
        </div>
      </div>
    </div>
  );
}
