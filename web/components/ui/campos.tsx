"use client";

/**
 * Campos com máscara brasileira, para a tela não repetir a formatação em cada formulário.
 *
 * Todos são controlados e devolvem o valor **como a API o quer**, não como foi digitado:
 * o telefone sai com a pontuação (o back-end normaliza para E.164), a data sai em ISO. A
 * regra de formatação em si mora em `lib/mascaras.ts`.
 */

import { useEffect, useState, type ComponentProps } from "react";
import { Input } from "./form";
import {
  cpfValido,
  dataDeISO,
  dataParaISO,
  mascaraCPF,
  mascaraData,
  mascaraRA,
  mascaraTelefone,
  somenteDigitos,
} from "@/lib/mascaras";

type BaseProps = Omit<ComponentProps<typeof Input>, "value" | "onChange">;

export function CampoCPF({
  value,
  onChange,
  ...rest
}: BaseProps & { value: string; onChange: (valor: string) => void }) {
  const digitos = somenteDigitos(value);
  // Só acusa erro com o CPF **completo**: marcar em vermelho a partir do primeiro dígito
  // faria o campo passar a digitação inteira gritando.
  const invalido = digitos.length === 11 && !cpfValido(digitos);
  return (
    <>
      <Input
        {...rest}
        inputMode="numeric"
        placeholder={rest.placeholder ?? "000.000.000-00"}
        value={mascaraCPF(value)}
        invalid={invalido}
        onChange={(e) => onChange(mascaraCPF(e.target.value))}
      />
      {invalido && (
        <span className="text-[11.5px] font-semibold text-danger">
          CPF inválido — confira os dígitos.
        </span>
      )}
    </>
  );
}

export function CampoTelefone({
  value,
  onChange,
  ...rest
}: BaseProps & { value: string; onChange: (valor: string) => void }) {
  return (
    <Input
      {...rest}
      inputMode="tel"
      placeholder={rest.placeholder ?? "(15) 99999-0000"}
      value={mascaraTelefone(value)}
      onChange={(e) => onChange(mascaraTelefone(e.target.value))}
    />
  );
}

export function CampoRA({
  value,
  onChange,
  ...rest
}: BaseProps & { value: string; onChange: (valor: string) => void }) {
  return (
    <Input
      {...rest}
      inputMode="numeric"
      placeholder={rest.placeholder ?? "Só números"}
      value={mascaraRA(value)}
      onChange={(e) => onChange(mascaraRA(e.target.value))}
    />
  );
}

/**
 * Data em `dd/mm/aaaa`, guardando ISO.
 *
 * Substitui o `<input type="date">`, que desenha no formato do **sistema operacional** —
 * numa máquina em inglês a secretaria via `mm/dd/aaaa`, e 03/04 vira 3 de abril ou 4 de
 * março dependendo de quem olha.
 *
 * O texto digitado vive em estado próprio porque uma data pela metade ("12/0") não tem
 * ISO: sem isso, o valor voltaria vazio do pai e apagaria o campo no meio da digitação.
 */
export function CampoData({
  value,
  onChange,
  ...rest
}: BaseProps & { value: string; onChange: (iso: string) => void }) {
  const [texto, setTexto] = useState(() => dataDeISO(value));

  // Só reescreve o texto quando o ISO de fora **discorda** do que está na tela — abrir
  // outro cadastro troca o campo; digitar, não.
  useEffect(() => {
    if (dataParaISO(texto) !== value) setTexto(dataDeISO(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const incompleta = somenteDigitos(texto).length === 8 && !dataParaISO(texto);

  return (
    <>
      <Input
        {...rest}
        inputMode="numeric"
        placeholder={rest.placeholder ?? "dd/mm/aaaa"}
        value={texto}
        invalid={incompleta}
        onChange={(e) => {
          const mascarado = mascaraData(e.target.value);
          setTexto(mascarado);
          onChange(dataParaISO(mascarado));
        }}
      />
      {incompleta && (
        <span className="text-[11.5px] font-semibold text-danger">
          Data inválida — use dd/mm/aaaa.
        </span>
      )}
    </>
  );
}
