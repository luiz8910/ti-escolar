"use client";

/**
 * Editor do expediente da secretaria (§6j).
 *
 * Este campo não é decorativo: é ele que decide se o assistente promete atendimento
 * "agora" ou "segunda a partir das 7h30" quando encaminha uma conversa. Por isso o
 * horário mora aqui, e não como um texto na base de conhecimento — a base responde a
 * quem *pergunta* o horário; aqui o horário **governa comportamento**.
 */

import type { ExpedienteEntrada } from "@/lib/admin";
import { Input } from "@/components/ui/form";
import { InfoIcon } from "@/components/ui/icons";

/** Dias no padrão ISO, na ordem em que a escola pensa a semana. */
export const DIAS: { valor: number; rotulo: string }[] = [
  { valor: 1, rotulo: "Seg" },
  { valor: 2, rotulo: "Ter" },
  { valor: 3, rotulo: "Qua" },
  { valor: 4, rotulo: "Qui" },
  { valor: 5, rotulo: "Sex" },
  { valor: 6, rotulo: "Sáb" },
  { valor: 7, rotulo: "Dom" },
];

/**
 * "Seg a Sex" para uma sequência contínua, "Seg, Qua, Sex" para dias soltos.
 *
 * É como a secretaria fala do próprio horário; a `descricao` que vem da API é pensada
 * para log (fuso incluído) e ocupa uma coluna inteira da lista.
 */
export function resumoDias(dias: number[]): string {
  const ordenados = [...new Set(dias)].sort((a, b) => a - b);
  if (ordenados.length === 0) return "Nenhum dia";
  if (ordenados.length === 7) return "Todos os dias";
  const rotulo = (d: number) => DIAS.find((x) => x.valor === d)?.rotulo ?? String(d);
  const continuo = ordenados.every((d, i) => i === 0 || d === ordenados[i - 1] + 1);
  if (continuo && ordenados.length >= 3) {
    return `${rotulo(ordenados[0])} a ${rotulo(ordenados[ordenados.length - 1])}`;
  }
  return ordenados.map(rotulo).join(", ");
}

export interface EstadoExpediente {
  dias: number[];
  inicio: string;
  fim: string;
}

export const EXPEDIENTE_PADRAO: EstadoExpediente = {
  dias: [1, 2, 3, 4, 5],
  inicio: "07:30",
  fim: "17:00",
};

/** Converte o estado do formulário no corpo que a API espera. */
export function paraEntrada(e: EstadoExpediente): ExpedienteEntrada {
  return {
    expediente_dias: e.dias,
    expediente_inicio: e.inicio,
    expediente_fim: e.fim,
  };
}

export function CamposExpediente({
  valor,
  onChange,
}: {
  valor: EstadoExpediente;
  onChange: (e: EstadoExpediente) => void;
}) {
  function alternarDia(dia: number) {
    const dias = valor.dias.includes(dia)
      ? valor.dias.filter((d) => d !== dia)
      : [...valor.dias, dia].sort((a, b) => a - b);
    onChange({ ...valor, dias });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Dias de atendimento">
        {DIAS.map((d) => {
          const ativo = valor.dias.includes(d.valor);
          return (
            <button
              key={d.valor}
              type="button"
              onClick={() => alternarDia(d.valor)}
              aria-pressed={ativo}
              className={
                "h-[38px] w-14 rounded-[9px] border text-[13px] transition-colors " +
                (ativo
                  ? "border-brand-600 bg-brand-50 font-semibold text-brand-700"
                  : "border-n-300 bg-white font-medium text-n-500 hover:border-n-400")
              }
            >
              {d.rotulo}
            </button>
          );
        })}
      </div>
      <div className="flex items-end gap-3">
        <div className="flex w-[140px] flex-col gap-1.5">
          <label htmlFor="expediente-inicio" className="text-[13px] font-semibold text-n-900">
            Abre às
          </label>
          <Input
            id="expediente-inicio"
            type="time"
            className="tabular-nums"
            value={valor.inicio}
            onChange={(e) => onChange({ ...valor, inicio: e.target.value })}
          />
        </div>
        <span className="flex h-[42px] items-center text-[13px] text-n-500">até</span>
        <div className="flex w-[140px] flex-col gap-1.5">
          <label htmlFor="expediente-fim" className="text-[13px] font-semibold text-n-900">
            Fecha às
          </label>
          <Input
            id="expediente-fim"
            type="time"
            className="tabular-nums"
            value={valor.fim}
            onChange={(e) => onChange({ ...valor, fim: e.target.value })}
          />
        </div>
      </div>
      <div className="flex gap-2.5 rounded-[10px] bg-brand-50/60 px-3.5 py-3 text-[13px] leading-[1.45] text-n-700">
        <InfoIcon size={16} className="mt-px flex-none text-brand-700" />
        <span>
          Fora desse horário o assistente encaminha a mensagem mesmo assim, mas avisa o
          responsável que o retorno será no próximo dia útil.
        </span>
      </div>
    </div>
  );
}
