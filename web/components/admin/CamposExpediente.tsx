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
import { Field, Input } from "@/components/ui/form";

/** Dias no padrão ISO, na ordem em que a escola pensa a semana. */
const DIAS: { valor: number; rotulo: string }[] = [
  { valor: 1, rotulo: "Seg" },
  { valor: 2, rotulo: "Ter" },
  { valor: 3, rotulo: "Qua" },
  { valor: 4, rotulo: "Qui" },
  { valor: 5, rotulo: "Sex" },
  { valor: 6, rotulo: "Sáb" },
  { valor: 7, rotulo: "Dom" },
];

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
    <Field
      label="Expediente da secretaria"
      hint="Fora deste horário o assistente encaminha assim mesmo, mas avisa o responsável que o retorno é no próximo dia útil."
    >
      <div className="flex flex-col gap-2.5">
        <div className="flex flex-wrap gap-1.5">
          {DIAS.map((d) => {
            const ativo = valor.dias.includes(d.valor);
            return (
              <button
                key={d.valor}
                type="button"
                onClick={() => alternarDia(d.valor)}
                aria-pressed={ativo}
                className={
                  "rounded-lg border px-2.5 py-1.5 text-[12.5px] font-semibold transition-colors " +
                  (ativo
                    ? "border-brand-500 bg-brand-50 text-brand-700"
                    : "border-n-300 bg-white text-n-500 hover:border-n-400")
                }
              >
                {d.rotulo}
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-2">
          <Input
            type="time"
            className="w-32"
            value={valor.inicio}
            onChange={(e) => onChange({ ...valor, inicio: e.target.value })}
          />
          <span className="text-[12.5px] text-n-500">até</span>
          <Input
            type="time"
            className="w-32"
            value={valor.fim}
            onChange={(e) => onChange({ ...valor, fim: e.target.value })}
          />
        </div>
      </div>
    </Field>
  );
}
