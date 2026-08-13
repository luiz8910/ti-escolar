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
  // Lista vazia devolve `total_paginas = 0`, e "1 / 0" é um contador que não faz sentido
  // para quem lê.
  const paginas = Math.max(1, meta.total_paginas);

  return (
    // Sem padding horizontal próprio: o paginador é o **rodapé do container**, e todos os
    // seus donos já são um `Card` com padding. O `px-4` que havia aqui somava ao do cartão
    // e a linha de topo nascia recuada dos dois lados, parecendo um traço solto no meio da
    // caixa em vez do fecho da lista.
    <div className="mt-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-t border-n-100 pt-3 text-[12.5px] text-n-500">
      <span className="whitespace-nowrap">
        {meta.total === 0
          ? `Nenhum ${rotulo.replace("(s)", "")}`
          : `${primeiro}–${ultimo} de ${meta.total} ${rotulo}`}
      </span>

      {/* O grupo da direita também quebra linha. Em Conversas o paginador mora numa coluna
          de 300 px, e um grupo rígido estourava a largura do cartão em vez de descer. */}
      <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
        <label className="flex shrink-0 items-center gap-2 font-semibold">
          Por página
          <Select
            className="w-[72px]"
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

        <div className="flex shrink-0 items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={meta.pagina <= 1}
            onClick={() => onPagina(meta.pagina - 1)}
          >
            Anterior
          </Button>
          <span className="whitespace-nowrap font-semibold text-n-600">
            {meta.pagina} / {paginas}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={meta.pagina >= paginas}
            onClick={() => onPagina(meta.pagina + 1)}
          >
            Próxima
          </Button>
        </div>
      </div>
    </div>
  );
}
