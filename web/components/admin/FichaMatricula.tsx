"use client";

/**
 * Ficha de matrícula do aluno — a tela que faltava.
 *
 * O back-end da ficha (§D1/D2/D3) existe desde a Onda 3 e **nunca teve interface**: dava
 * para gravar por API e nada mais. Este componente é o que o apontamento de 10/08 chama
 * de "cadastro dados obrigatórios: ver ficha em anexo".
 *
 * Duas escolhas que valem explicação:
 *
 * - **A filiação não é digitada aqui.** Ela é derivada dos responsáveis vinculados ao
 *   aluno. A ficha nasceu com `filiacao1_*`/`filiacao2_*` como texto solto — uma segunda
 *   cópia dos mesmos dados que moram no cadastro do responsável, livre para divergir. A
 *   aba mostra quem está vinculado e manda gerenciar em Responsáveis.
 * - **O laudo tem três estados** (não · sim · em investigação), como as três caixas da
 *   ficha física. Texto livre não distingue "não tem" de "está sendo investigado", e a
 *   diferença é uma pendência que a escola precisa acompanhar.
 *
 * Os campos com \\* são exigidos pelo back-end ao salvar — não ao cadastrar o aluno. Quem
 * cadastra em massa cria o aluno só com nome e série; a ficha é o momento em que a
 * secretaria tem a papelada na mão.
 */

import { useCallback, useEffect, useState } from "react";
import {
  Aluno,
  CamposFicha,
  definirFotoAluno,
  obterFicha,
  removerFotoAluno,
  salvarFicha,
  urlFotoAluno,
} from "@/lib/admin";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/components/ui/cn";

const ABAS = [
  { chave: "aluno", rotulo: "Aluno" },
  { chave: "responsaveis", rotulo: "Responsáveis" },
  { chave: "obrigatorios", rotulo: "Dados obrigatórios" },
  { chave: "autorizacoes", rotulo: "Autorizações" },
] as const;
type Aba = (typeof ABAS)[number]["chave"];

// Da ficha física: as cinco categorias de cor/raça do censo escolar.
const CORES_RACA = ["Branca", "Parda", "Preta", "Amarela", "Indígena"];
const SEXOS = [
  { valor: "F", rotulo: "Feminino" },
  { valor: "M", rotulo: "Masculino" },
];
const LAUDO = [
  { valor: "nao", rotulo: "Não possui" },
  { valor: "sim", rotulo: "Sim (informar CID)" },
  { valor: "em_investigacao", rotulo: "Em investigação" },
];

function texto(campos: CamposFicha, chave: string): string {
  const v = campos[chave];
  return typeof v === "string" ? v : "";
}

function marcado(campos: CamposFicha, chave: string): boolean {
  return campos[chave] === true || campos[chave] === "sim";
}

export function FichaMatricula({
  aluno,
  onFechar,
  onSalvo,
}: {
  aluno: Aluno;
  onFechar: () => void;
  onSalvo: () => Promise<void>;
}) {
  const toast = useToast();
  const [aba, setAba] = useState<Aba>("aluno");
  const [campos, setCampos] = useState<CamposFicha>({});
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  const set = (chave: string, valor: string | boolean) =>
    setCampos((atual) => ({ ...atual, [chave]: valor }));

  useEffect(() => {
    obterFicha(aluno.id)
      .then((f) => setCampos(f?.campos ?? {}))
      .catch(() => toast({ tone: "danger", title: "Falha ao carregar a ficha." }))
      .finally(() => setCarregando(false));
  }, [aluno.id, toast]);

  async function salvar() {
    setSalvando(true);
    setErro("");
    try {
      await salvarFicha(aluno.id, campos);
      toast({ tone: "success", title: "Ficha salva." });
      await onSalvo();
      onFechar();
    } catch (e) {
      // O back-end devolve os campos que faltam numa mensagem só — mostrar no formulário,
      // e não num toast que some, é o que permite corrigir sem reabrir a ficha.
      setErro(e instanceof Error ? e.message : "Falha ao salvar a ficha.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      open
      onClose={onFechar}
      title={`Ficha de matrícula — ${aluno.nome}`}
      className="max-w-3xl"
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onFechar}>
            Cancelar
          </Button>
          <Button size="sm" onClick={salvar} disabled={salvando || carregando}>
            {salvando ? "Salvando…" : "Salvar ficha"}
          </Button>
        </>
      }
    >
      <div className="flex gap-1 rounded-lg bg-n-100 p-1">
        {ABAS.map((a) => (
          <button
            key={a.chave}
            type="button"
            onClick={() => setAba(a.chave)}
            className={cn(
              "flex-1 rounded-md px-3 py-1.5 text-[12.5px] font-semibold transition-colors",
              aba === a.chave
                ? "bg-white text-n-900 shadow-sm"
                : "text-n-500 hover:text-n-700",
            )}
          >
            {a.rotulo}
          </button>
        ))}
      </div>

      {carregando ? (
        <p className="py-6 text-center text-sm text-n-400">Carregando a ficha…</p>
      ) : (
        <div className="mt-4 flex flex-col gap-3">
          {aba === "aluno" && (
            <AbaAluno aluno={aluno} campos={campos} set={set} onSalvo={onSalvo} />
          )}
          {aba === "responsaveis" && <AbaResponsaveis aluno={aluno} />}
          {aba === "obrigatorios" && <AbaObrigatorios campos={campos} set={set} />}
          {aba === "autorizacoes" && <AbaAutorizacoes campos={campos} set={set} />}
        </div>
      )}

      {erro && (
        <p className="mt-3 rounded-lg bg-danger-soft px-3 py-2 text-[12.5px] text-danger">
          {erro}
        </p>
      )}
    </Modal>
  );
}

// --------------------------------------------------------------------------- //
function AbaAluno({
  aluno,
  campos,
  set,
  onSalvo,
}: {
  aluno: Aluno;
  campos: CamposFicha;
  set: (chave: string, valor: string) => void;
  onSalvo: () => Promise<void>;
}) {
  return (
    <>
      <FotoDoAluno aluno={aluno} onMudou={onSalvo} />
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Field label="CPF *" htmlFor="fm-cpf">
          <Input
            id="fm-cpf"
            value={texto(campos, "cpf")}
            onChange={(e) => set("cpf", e.target.value)}
            placeholder="000.000.000-00"
            inputMode="numeric"
          />
        </Field>
        <Field label="RA / RM *" htmlFor="fm-ra">
          <Input
            id="fm-ra"
            value={texto(campos, "ra_rm")}
            onChange={(e) => set("ra_rm", e.target.value)}
          />
        </Field>
        <Field label="Data de nascimento *" htmlFor="fm-nasc">
          <Input
            id="fm-nasc"
            type="date"
            value={texto(campos, "data_nascimento")}
            onChange={(e) => set("data_nascimento", e.target.value)}
          />
        </Field>
        <Field label="Sexo *" htmlFor="fm-sexo">
          <Select
            id="fm-sexo"
            value={texto(campos, "sexo")}
            onChange={(e) => set("sexo", e.target.value)}
          >
            <option value="">Selecione…</option>
            {SEXOS.map((s) => (
              <option key={s.valor} value={s.valor}>
                {s.rotulo}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Cidade de nascimento" htmlFor="fm-cidade">
          <Input
            id="fm-cidade"
            value={texto(campos, "cidade_natal")}
            onChange={(e) => set("cidade_natal", e.target.value)}
          />
        </Field>
        <Field label="Cartão do SUS" htmlFor="fm-sus">
          <Input
            id="fm-sus"
            value={texto(campos, "cartao_sus")}
            onChange={(e) => set("cartao_sus", e.target.value)}
          />
        </Field>
      </div>
      <Field label="Endereço completo *" htmlFor="fm-end">
        <Input
          id="fm-end"
          value={texto(campos, "endereco")}
          onChange={(e) => set("endereco", e.target.value)}
          placeholder="Rua, número, bairro, cidade"
        />
      </Field>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Field label="Com quem mora" htmlFor="fm-mora">
          <Input
            id="fm-mora"
            value={texto(campos, "com_quem_mora")}
            onChange={(e) => set("com_quem_mora", e.target.value)}
          />
        </Field>
        <Field label="Irmãos na escola" htmlFor="fm-irmaos">
          <Input
            id="fm-irmaos"
            value={texto(campos, "irmaos_na_escola")}
            onChange={(e) => set("irmaos_na_escola", e.target.value)}
          />
        </Field>
      </div>
      <p className="text-[11.5px] text-n-400">
        Campos com <b>*</b> são exigidos para salvar a ficha. O cadastro do aluno em si
        precisa só de nome e série — a ficha é preenchida quando a papelada chega.
      </p>
    </>
  );
}

// --------------------------------------------------------------------------- //
function FotoDoAluno({
  aluno,
  onMudou,
}: {
  aluno: Aluno;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [url, setUrl] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [temFoto, setTemFoto] = useState(aluno.tem_foto);

  const carregar = useCallback(async () => {
    if (!temFoto) {
      setUrl(null);
      return;
    }
    setUrl(await urlFotoAluno(aluno.id));
  }, [aluno.id, temFoto]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  // O blob fica na memória da aba até ser revogado.
  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [url]);

  async function enviar(e: React.ChangeEvent<HTMLInputElement>) {
    const arquivo = e.target.files?.[0];
    if (!arquivo) return;
    setOcupado(true);
    try {
      await definirFotoAluno(aluno.id, arquivo);
      setTemFoto(true);
      await onMudou();
      toast({ tone: "success", title: "Foto atualizada." });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao enviar a foto.",
      });
    } finally {
      setOcupado(false);
      e.target.value = "";
    }
  }

  async function remover() {
    setOcupado(true);
    try {
      await removerFotoAluno(aluno.id);
      setTemFoto(false);
      await onMudou();
      toast({ tone: "success", title: "Foto removida." });
    } catch (err) {
      toast({
        tone: "danger",
        title: err instanceof Error ? err.message : "Falha ao remover a foto.",
      });
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="flex items-center gap-4 rounded-xl border border-n-200 p-3">
      <div className="flex h-20 w-20 flex-none items-center justify-center overflow-hidden rounded-lg bg-n-100">
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element -- blob URL de endpoint
          // autenticado: o <Image> do Next tentaria otimizar uma URL que só existe nesta aba.
          <img src={url} alt={`Foto de ${aluno.nome}`} className="h-full w-full object-cover" />
        ) : (
          <span className="text-[11px] text-n-400">sem foto</span>
        )}
      </div>
      <div className="flex flex-col gap-1.5">
        <div className="flex gap-2">
          <label
            className={cn(
              "cursor-pointer rounded-lg border border-n-200 px-3 py-1.5 text-[12.5px] font-semibold text-n-700 hover:bg-n-50",
              ocupado && "pointer-events-none opacity-50",
            )}
          >
            {temFoto ? "Trocar foto" : "Enviar foto"}
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="sr-only"
              onChange={enviar}
            />
          </label>
          {temFoto && (
            <button
              type="button"
              onClick={remover}
              disabled={ocupado}
              className="text-[12.5px] font-semibold text-danger hover:underline"
            >
              Remover
            </button>
          )}
        </div>
        <p className="text-[11.5px] text-n-400">
          Opcional. JPEG, PNG ou WebP, até 5 MB.
        </p>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
function AbaResponsaveis({ aluno }: { aluno: Aluno }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-[12.5px] text-brand-900">
        A filiação da ficha vem <b>daqui</b>: dos responsáveis vinculados ao aluno. Não é
        digitada de novo, para não haver duas versões do mesmo dado. Para incluir ou trocar
        alguém — inclusive um <b>responsável legal por termo de guarda</b> — use o botão
        &ldquo;Responsáveis&rdquo; na lista de alunos.
      </p>
      <ul className="flex flex-col gap-1.5">
        {aluno.responsaveis.map((r) => (
          <li
            key={r.id}
            className="flex flex-wrap items-center gap-2 rounded-[10px] bg-n-50 px-3 py-2 text-[13px]"
          >
            <span className="font-medium text-n-800">{r.nome}</span>
            <span
              className={cn(
                "text-[11px] font-semibold",
                r.tipo_filiacao === "responsavel_legal" ? "text-accent" : "text-n-400",
              )}
            >
              {r.tipo_filiacao === "responsavel_legal"
                ? "termo de guarda"
                : r.tipo_filiacao_rotulo.toLowerCase() || "filiação não informada"}
            </span>
            <span className="ml-auto font-mono text-xs text-n-500">{r.telefone}</span>
            {r.cpf_formatado && (
              <span className="font-mono text-xs text-n-400">{r.cpf_formatado}</span>
            )}
          </li>
        ))}
        {aluno.responsaveis.length === 0 && (
          <li className="px-1 py-2 text-sm text-n-400">
            Nenhum responsável vinculado — a ficha sairá sem filiação.
          </li>
        )}
      </ul>
    </div>
  );
}

// --------------------------------------------------------------------------- //
function AbaObrigatorios({
  campos,
  set,
}: {
  campos: CamposFicha;
  set: (chave: string, valor: string | boolean) => void;
}) {
  const laudo = texto(campos, "laudo_status");
  return (
    <>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Field label="Cor / raça *" htmlFor="fm-cor">
          <Select
            id="fm-cor"
            value={texto(campos, "cor_raca")}
            onChange={(e) => set("cor_raca", e.target.value)}
          >
            <option value="">Selecione…</option>
            {CORES_RACA.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="NIS (se recebe Bolsa Família)" htmlFor="fm-nis">
          <Input
            id="fm-nis"
            value={texto(campos, "nis")}
            onChange={(e) => set("nis", e.target.value)}
          />
        </Field>
      </div>

      <Marcavel
        rotulo="Recebe Bolsa Família"
        marcado={marcado(campos, "bolsa_familia")}
        onChange={(v) => set("bolsa_familia", v)}
      />

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Field label="Possui deficiência? Qual?" htmlFor="fm-def">
          <Input
            id="fm-def"
            value={texto(campos, "deficiencia")}
            onChange={(e) => set("deficiencia", e.target.value)}
            placeholder="Deixe em branco se não possui"
          />
        </Field>
        <Field label="Necessidade especial? Qual?" htmlFor="fm-nec">
          <Input
            id="fm-nec"
            value={texto(campos, "necessidade_especial")}
            onChange={(e) => set("necessidade_especial", e.target.value)}
          />
        </Field>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Field label="Laudo médico" htmlFor="fm-laudo">
          <Select
            id="fm-laudo"
            value={laudo}
            onChange={(e) => set("laudo_status", e.target.value)}
          >
            <option value="">Não informado</option>
            {LAUDO.map((l) => (
              <option key={l.valor} value={l.valor}>
                {l.rotulo}
              </option>
            ))}
          </Select>
        </Field>
        {/* O CID só aparece com "sim" — e o back-end limpa o campo nos outros estados,
            para a ficha não afirmar um diagnóstico que a escola acabou de negar. */}
        {laudo === "sim" && (
          <Field label="CID" htmlFor="fm-cid">
            <Input
              id="fm-cid"
              value={texto(campos, "laudo_cid")}
              onChange={(e) => set("laudo_cid", e.target.value)}
              placeholder="Ex.: F84.0"
            />
          </Field>
        )}
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Field label="Restrição alimentar? Qual?" htmlFor="fm-rest">
          <Input
            id="fm-rest"
            value={texto(campos, "restricao_alimentar")}
            onChange={(e) => set("restricao_alimentar", e.target.value)}
          />
        </Field>
        <Field label="Alergia? Qual?" htmlFor="fm-alerg">
          <Input
            id="fm-alerg"
            value={texto(campos, "alergia")}
            onChange={(e) => set("alergia", e.target.value)}
          />
        </Field>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Field label="UBS de referência" htmlFor="fm-ubs">
          <Input
            id="fm-ubs"
            value={texto(campos, "ubs")}
            onChange={(e) => set("ubs", e.target.value)}
          />
        </Field>
        <Field label="Convênio" htmlFor="fm-conv">
          <Input
            id="fm-conv"
            value={texto(campos, "convenio")}
            onChange={(e) => set("convenio", e.target.value)}
          />
        </Field>
      </div>

      <Field label="Tratamento / medicação em uso" htmlFor="fm-trat">
        <Textarea
          id="fm-trat"
          rows={2}
          value={texto(campos, "tratamento_medicacao")}
          onChange={(e) => set("tratamento_medicacao", e.target.value)}
        />
      </Field>

      <p className="rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-[11.5px] text-danger">
        Os campos desta aba são <b>dados sensíveis de saúde de menor</b> (LGPD, arts. 11 e
        14). Preencha só o necessário e não repita aqui o que já está no laudo anexado.
      </p>
    </>
  );
}

// --------------------------------------------------------------------------- //
function AbaAutorizacoes({
  campos,
  set,
}: {
  campos: CamposFicha;
  set: (chave: string, valor: string | boolean) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <Marcavel
        rotulo="Autoriza transporte por van"
        marcado={marcado(campos, "autorizacao_van")}
        onChange={(v) => set("autorizacao_van", v)}
      />
      <Marcavel
        rotulo="Autoriza retirada por terceiros"
        descricao="Quem pode retirar precisa estar cadastrado como responsável."
        marcado={marcado(campos, "autorizacao_retirada")}
        onChange={(v) => set("autorizacao_retirada", v)}
      />
      <Marcavel
        rotulo="Autoriza uso de imagem"
        descricao="Fotos e vídeos em comunicados e redes da escola."
        marcado={marcado(campos, "autorizacao_imagem")}
        onChange={(v) => set("autorizacao_imagem", v)}
      />
    </div>
  );
}

function Marcavel({
  rotulo,
  descricao,
  marcado,
  onChange,
}: {
  rotulo: string;
  descricao?: string;
  marcado: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-2.5 rounded-lg border border-n-200 bg-n-50 p-3 text-[13px] text-n-700">
      <input
        type="checkbox"
        className="mt-0.5"
        checked={marcado}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        <b>{rotulo}</b>
        {descricao && <span className="block text-[11.5px] text-n-500">{descricao}</span>}
      </span>
    </label>
  );
}
