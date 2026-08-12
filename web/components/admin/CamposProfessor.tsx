"use client";

/**
 * Campos do cadastro funcional do professor, em um lugar só.
 *
 * O cadastro **mínimo** continua sendo nome + telefone — é o que a escola tem no primeiro
 * dia, e exigir CPF e matrícula de saída travaria o cadastro de quem já está dando aula.
 * Por isso este bloco é recolhido por padrão no formulário de criação e aberto na edição,
 * onde a secretaria está justamente completando o registro.
 *
 * Dois campos não são cadastro, são comportamento, e a tela diz isso em texto:
 * `titular=false` monta a lista de quem cobre falta (§I1), e `telefone_2` **não** recebe
 * disparo nenhum.
 */

import { DadosProfessor } from "@/lib/admin";
import { Input, Field } from "@/components/ui/form";

export function CamposProfessor({
  dados,
  onChange,
}: {
  dados: DadosProfessor;
  onChange: (dados: DadosProfessor) => void;
}) {
  const set = <K extends keyof DadosProfessor>(campo: K, valor: DadosProfessor[K]) =>
    onChange({ ...dados, [campo]: valor });

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Field label="CPF" htmlFor="prof-cpf">
          <Input
            id="prof-cpf"
            value={dados.cpf}
            onChange={(e) => set("cpf", e.target.value)}
            placeholder="000.000.000-00"
            inputMode="numeric"
          />
        </Field>
        <Field label="Data de nascimento" htmlFor="prof-nasc">
          <Input
            id="prof-nasc"
            type="date"
            value={dados.data_nascimento}
            onChange={(e) => set("data_nascimento", e.target.value)}
          />
        </Field>
        <Field label="Matrícula funcional" htmlFor="prof-mat">
          <Input
            id="prof-mat"
            value={dados.matricula}
            onChange={(e) => set("matricula", e.target.value)}
            placeholder="Número na rede"
          />
        </Field>
        <Field label="E-mail" htmlFor="prof-email">
          <Input
            id="prof-email"
            type="email"
            value={dados.email}
            onChange={(e) => set("email", e.target.value)}
            placeholder="professor@escola.test"
          />
        </Field>
      </div>

      <Field label="Endereço completo" htmlFor="prof-end">
        <Input
          id="prof-end"
          value={dados.endereco}
          onChange={(e) => set("endereco", e.target.value)}
          placeholder="Rua, número, bairro, cidade"
        />
      </Field>

      <Field label="Telefone 2 (emergência)" htmlFor="prof-tel2">
        <Input
          id="prof-tel2"
          value={dados.telefone_2}
          onChange={(e) => set("telefone_2", e.target.value)}
          placeholder="(15) 98888-7777"
        />
      </Field>
      <p className="-mt-1 text-[11.5px] text-n-400">
        O telefone 2 é só contato de emergência: <b>não</b> recebe recado, mural nem chamada
        de eventual. Quem recebe é o WhatsApp principal.
      </p>

      <div className="flex flex-col gap-2 rounded-lg border border-n-200 bg-n-50 p-3">
        <label className="flex items-start gap-2.5 text-[13px] text-n-700">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={!dados.titular}
            onChange={(e) => set("titular", !e.target.checked)}
          />
          <span>
            <b>Professor eventual</b> (substituto)
            <span className="block text-[11.5px] text-n-500">
              Entra na lista de quem a secretaria pode chamar quando um professor falta.
              Deixe desmarcado para o professor titular da turma.
            </span>
          </span>
        </label>
        <label className="flex items-start gap-2.5 text-[13px] text-n-700">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={dados.educacao_fisica}
            onChange={(e) => set("educacao_fisica", e.target.checked)}
          />
          <span>Professor de educação física</span>
        </label>
      </div>
    </div>
  );
}
