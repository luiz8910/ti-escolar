"use client";

/**
 * Grade de horário da turma — **os dois formatos**, decisão B do plano de 10/08.
 *
 * A escola pediu para ver os dois funcionando antes de escolher, então o seletor troca
 * entre eles e **os dois gravam na mesma coluna JSON**. É isso que torna a escolha barata
 * depois: descartar um é apagar este bloco de tela, não migrar dado.
 *
 * - **Turno**: entrada, saída e o intervalo. Quatro campos, que é o que a secretaria tem
 *   escrito hoje em algum lugar.
 * - **Aula a aula**: um bloco por dia e horário, com o **intervalo como bloco** — o
 *   apontamento pedia "grade de horário com intervalo incluso", e tratá-lo à parte faria
 *   a carga horária ignorá-lo.
 *
 * Trocar de formato **não apaga** o que foi preenchido no outro: os dois convivem no
 * estado até salvar, e só o formato escolhido é enviado. Quem está comparando os dois
 * perderia o trabalho a cada clique.
 */

import { useState } from "react";
import { BlocoGrade, DIAS_SEMANA, FormatoGrade, Grade } from "@/lib/admin";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/form";
import { cn } from "@/components/ui/cn";

function minutos(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

/** Carga semanal de aula (sem intervalo), para o rodapé conferir a soma. */
function cargaSemanal(blocos: BlocoGrade[]): string {
  const total = blocos
    .filter((b) => b.tipo === "aula")
    .reduce((soma, b) => soma + Math.max(0, minutos(b.fim) - minutos(b.inicio)), 0);
  const horas = Math.floor(total / 60);
  const resto = total % 60;
  return resto ? `${horas}h${String(resto).padStart(2, "0")}` : `${horas}h`;
}

export function GradeHorario({
  grade,
  onChange,
}: {
  grade: Grade;
  onChange: (g: Grade) => void;
}) {
  const formato: FormatoGrade = grade.formato ?? "turno";
  // Guarda o outro formato enquanto a pessoa compara — ver o docstring.
  const [rascunho, setRascunho] = useState<Grade>(grade);

  function trocarFormato(novo: FormatoGrade) {
    const combinado = { ...rascunho, ...grade, formato: novo };
    setRascunho(combinado);
    onChange(combinado);
  }

  function set(campo: keyof Grade, valor: unknown) {
    const atualizado = { ...grade, formato, [campo]: valor };
    setRascunho(atualizado);
    onChange(atualizado);
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-n-200 p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[13px] font-bold text-n-800">Grade de horário</span>
        <div className="flex gap-1 rounded-lg bg-n-100 p-1">
          {(
            [
              { valor: "turno", rotulo: "Turno e intervalo" },
              { valor: "aulas", rotulo: "Aula a aula" },
            ] as const
          ).map((f) => (
            <button
              key={f.valor}
              type="button"
              onClick={() => trocarFormato(f.valor)}
              className={cn(
                "rounded-md px-3 py-1.5 text-[12px] font-semibold transition-colors",
                formato === f.valor
                  ? "bg-white text-n-900 shadow-sm"
                  : "text-n-500 hover:text-n-700",
              )}
            >
              {f.rotulo}
            </button>
          ))}
        </div>
      </div>

      {formato === "turno" ? (
        <GradeTurno grade={grade} set={set} />
      ) : (
        <GradeAulas
          blocos={grade.blocos ?? []}
          onChange={(blocos) => set("blocos", blocos)}
        />
      )}

      <p className="text-[11.5px] text-n-400">
        Os dois formatos gravam no mesmo lugar — dá para experimentar um, salvar, e trocar
        depois sem perder o cadastro da turma.
      </p>
    </div>
  );
}

function GradeTurno({
  grade,
  set,
}: {
  grade: Grade;
  set: (campo: keyof Grade, valor: unknown) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Field label="Entrada" htmlFor="g-inicio">
        <Input
          id="g-inicio"
          type="time"
          value={grade.inicio ?? ""}
          onChange={(e) => set("inicio", e.target.value)}
        />
      </Field>
      <Field label="Saída" htmlFor="g-fim">
        <Input
          id="g-fim"
          type="time"
          value={grade.fim ?? ""}
          onChange={(e) => set("fim", e.target.value)}
        />
      </Field>
      <Field label="Intervalo às" htmlFor="g-int">
        <Input
          id="g-int"
          type="time"
          value={grade.intervalo_inicio ?? ""}
          onChange={(e) => set("intervalo_inicio", e.target.value)}
        />
      </Field>
      <Field label="Duração (min)" htmlFor="g-intmin">
        <Input
          id="g-intmin"
          type="number"
          min={0}
          value={grade.intervalo_minutos ?? 0}
          onChange={(e) => set("intervalo_minutos", Number(e.target.value))}
        />
      </Field>
    </div>
  );
}

function GradeAulas({
  blocos,
  onChange,
}: {
  blocos: BlocoGrade[];
  onChange: (b: BlocoGrade[]) => void;
}) {
  function adicionar() {
    // Herda o dia e emenda no fim do último bloco: montar uma grade é encadear horários,
    // e recomeçar do zero a cada linha é o que torna a tela cansativa.
    const ultimo = blocos[blocos.length - 1];
    onChange([
      ...blocos,
      {
        dia: ultimo?.dia ?? 1,
        inicio: ultimo?.fim ?? "07:30",
        fim: "",
        tipo: "aula",
        rotulo: "",
      },
    ]);
  }

  function alterar(indice: number, campo: keyof BlocoGrade, valor: unknown) {
    onChange(blocos.map((b, i) => (i === indice ? { ...b, [campo]: valor } : b)));
  }

  return (
    <div className="flex flex-col gap-2">
      {blocos.length > 0 && (
        <div className="flex flex-col gap-1.5">
          {blocos.map((bloco, i) => (
            <div key={i} className="flex flex-wrap items-end gap-1.5">
              <Select
                className="w-[86px]"
                aria-label="Dia"
                value={bloco.dia}
                onChange={(e) => alterar(i, "dia", Number(e.target.value))}
              >
                {DIAS_SEMANA.map((d) => (
                  <option key={d.valor} value={d.valor}>
                    {d.curto}
                  </option>
                ))}
              </Select>
              <Input
                className="w-[104px]"
                type="time"
                aria-label="Início"
                value={bloco.inicio}
                onChange={(e) => alterar(i, "inicio", e.target.value)}
              />
              <Input
                className="w-[104px]"
                type="time"
                aria-label="Fim"
                value={bloco.fim}
                onChange={(e) => alterar(i, "fim", e.target.value)}
              />
              <Select
                className="w-[116px]"
                aria-label="Tipo"
                value={bloco.tipo}
                onChange={(e) => alterar(i, "tipo", e.target.value)}
              >
                <option value="aula">Aula</option>
                <option value="intervalo">Intervalo</option>
              </Select>
              <Input
                className="min-w-[120px] flex-1"
                aria-label="Rótulo"
                placeholder={bloco.tipo === "intervalo" ? "Recreio" : "Disciplina"}
                value={bloco.rotulo}
                onChange={(e) => alterar(i, "rotulo", e.target.value)}
              />
              <button
                type="button"
                onClick={() => onChange(blocos.filter((_, j) => j !== i))}
                className="pb-2 text-xs font-semibold text-danger hover:underline"
              >
                Remover
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" size="sm" variant="secondary" onClick={adicionar}>
          + Adicionar bloco
        </Button>
        {blocos.length > 0 && (
          <span className="text-[11.5px] text-n-400">
            {blocos.length} bloco(s) · <b>{cargaSemanal(blocos)}</b> de aula por semana
            (intervalo não conta)
          </span>
        )}
      </div>
    </div>
  );
}
