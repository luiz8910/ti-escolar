"use client";

/**
 * Cadastro civil e de contato do responsável, em um lugar só.
 *
 * O mínimo continua sendo **nome + telefone**: é o que a escola tem quando a mãe manda o
 * número pelo WhatsApp, e é o que a importação em massa produz. Exigir CPF de saída
 * travaria justamente o cadastro que o bot alimenta sozinho — por isso este bloco é
 * recolhido na criação e aberto na edição.
 *
 * **Termo de guarda** não é um formulário separado: é escolher *Responsável legal* no tipo
 * de filiação. A pessoa vira um responsável como qualquer outro — recebe disparo, é
 * reconhecida no WhatsApp e conta na cobertura da turma. Antes era um booleano na ficha do
 * aluno, e quem respondia pela criança ficava invisível para o canal.
 */

import { DadosResponsavel, TipoFiliacao, TIPOS_FILIACAO } from "@/lib/admin";
import { Input, Select, Field } from "@/components/ui/form";

export function CamposResponsavel({
  dados,
  onChange,
  idPrefixo = "resp",
}: {
  dados: DadosResponsavel;
  onChange: (dados: DadosResponsavel) => void;
  /** Evita ids duplicados quando dois formulários coexistem na mesma tela. */
  idPrefixo?: string;
}) {
  const set = <K extends keyof DadosResponsavel>(
    campo: K,
    valor: DadosResponsavel[K],
  ) => onChange({ ...dados, [campo]: valor });

  const guarda = dados.tipo_filiacao === "responsavel_legal";

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Field label="CPF" htmlFor={`${idPrefixo}-cpf`}>
          <Input
            id={`${idPrefixo}-cpf`}
            value={dados.cpf}
            onChange={(e) => set("cpf", e.target.value)}
            placeholder="000.000.000-00"
            inputMode="numeric"
          />
        </Field>
        <Field label="Tipo de filiação" htmlFor={`${idPrefixo}-filiacao`}>
          <Select
            id={`${idPrefixo}-filiacao`}
            value={dados.tipo_filiacao}
            onChange={(e) =>
              set("tipo_filiacao", e.target.value as TipoFiliacao | "")
            }
          >
            <option value="">Não informado</option>
            {TIPOS_FILIACAO.map((t) => (
              <option key={t.valor} value={t.valor}>
                {t.rotulo}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {guarda && (
        <p className="-mt-1 rounded-lg border border-accent/30 bg-accent-soft px-3 py-2 text-[12px] text-[#7a5208]">
          <b>Termo de guarda.</b> Esta pessoa passa a valer como responsável para todos os
          efeitos: recebe os avisos da escola, é reconhecida na conversa do WhatsApp e conta
          na cobertura de contatos da turma. Vincule-a ao aluno na tela de Alunos.
        </p>
      )}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Field label="Data de nascimento" htmlFor={`${idPrefixo}-nasc`}>
          <Input
            id={`${idPrefixo}-nasc`}
            type="date"
            value={dados.data_nascimento}
            onChange={(e) => set("data_nascimento", e.target.value)}
          />
        </Field>
        <Field label="E-mail" htmlFor={`${idPrefixo}-email`}>
          <Input
            id={`${idPrefixo}-email`}
            type="email"
            value={dados.email}
            onChange={(e) => set("email", e.target.value)}
            placeholder="responsavel@email.com"
          />
        </Field>
        <Field label="Local de trabalho" htmlFor={`${idPrefixo}-trab`}>
          <Input
            id={`${idPrefixo}-trab`}
            value={dados.local_trabalho}
            onChange={(e) => set("local_trabalho", e.target.value)}
          />
        </Field>
        <Field label="Telefone do trabalho" htmlFor={`${idPrefixo}-teltrab`}>
          <Input
            id={`${idPrefixo}-teltrab`}
            value={dados.telefone_trabalho}
            onChange={(e) => set("telefone_trabalho", e.target.value)}
            placeholder="(15) 3333-4444"
          />
        </Field>
      </div>

      <Field label="Telefone 2 (emergência)" htmlFor={`${idPrefixo}-tel2`}>
        <Input
          id={`${idPrefixo}-tel2`}
          value={dados.telefone_2}
          onChange={(e) => set("telefone_2", e.target.value)}
          placeholder="(15) 98888-7777"
        />
      </Field>
      <p className="-mt-1 text-[11.5px] text-n-400">
        O telefone principal é o <b>único</b> que recebe os avisos da escola e conversa com
        o assistente. O telefone 2 e o do trabalho são contato de emergência: não entram em
        disparo.
      </p>
    </div>
  );
}
