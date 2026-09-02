"use client";

// Onboarding do WhatsApp de uma escola (§9e.3) — o roteiro do console da Meta virado tela.
//
// O go-live do canal custou três dias de depuração por causa de passos que **não dão erro
// em lugar nenhum**: app não publicado, WABA não inscrita no app, `phone_number_id` não
// cadastrado na escola. O valor desta tela não é economizar cliques; é fazer cada um
// desses estados aparecer em vermelho, com o motivo escrito, em vez de virar um webhook
// mudo que ninguém sabe interpretar.
//
// O que ela **não** automatiza é o que não tem API: comprar o chip, pôr num aparelho e ler
// o código de 6 dígitos. Por isso o fluxo para no campo do código e espera uma pessoa.

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  cadastrarNumeroNaMeta,
  concluirOnboarding,
  confirmarCodigoDeVerificacao,
  desvincularNumeroDaEscola,
  DiagnosticoWhatsApp,
  diagnosticarWhatsApp,
  getSessao,
  inscreverNumeroNaCloudApi,
  logout,
  pedirCodigoDeVerificacao,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Field, Input, Select } from "@/components/ui/form";
import { ConfirmDialog } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";

/** Rótulo humano de cada etapa que a Meta reconhece. */
const ETAPAS: Record<string, { rotulo: string; tone: "neutral" | "warning" | "success" | "danger" }> = {
  ausente: { rotulo: "Sem número", tone: "neutral" },
  nao_verificado: { rotulo: "Não verificado", tone: "warning" },
  nao_registrado: { rotulo: "Verificado, não inscrito", tone: "warning" },
  registrado: { rotulo: "Inscrito", tone: "success" },
  desconhecida: { rotulo: "Estado desconhecido", tone: "danger" },
};

export default function OnboardingWhatsAppPage() {
  const router = useRouter();
  const toast = useToast();
  // A escola vem de `?tenant=`, não de um segmento dinâmico: com `output: "export"` uma
  // rota `[tenantId]` exigiria `generateStaticParams()`, e os ids só existem em execução.
  // Mesmo caminho de `/admin/escolas/detalhe`.
  const [tenantId, setTenantId] = useState("");
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [diag, setDiag] = useState<DiagnosticoWhatsApp | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState("");

  const recarregar = useCallback(async (id: string) => {
    setErro("");
    try {
      setDiag(await diagnosticarWhatsApp(id));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao consultar a Meta.");
    }
  }, []);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    if (s.usuario.papel !== "super_admin") {
      router.replace("/admin");
      return;
    }
    setUsuario(s.usuario);
    const id = new URLSearchParams(window.location.search).get("tenant") ?? "";
    setTenantId(id);
    if (!id) {
      setErro("Escola não informada. Abra esta tela pela lista de escolas.");
      setCarregando(false);
      return;
    }
    recarregar(id).finally(() => setCarregando(false));
  }, [router, recarregar]);

  if (!usuario) return null;
  const atualizar = () => recarregar(tenantId);

  return (
    <AppShell
      exigeEscola={false}
      title="WhatsApp da escola"
      user={{ name: usuario.nome, role: "Super Admin" }}
      isSuperAdmin
      onLogout={() => {
        logout();
        router.replace("/admin/login");
      }}
    >
      <div className="flex flex-col gap-[18px]">
        <a href="/admin/escolas" className="text-xs font-semibold text-brand-600 hover:underline">
          ← Voltar para as escolas
        </a>

        {carregando ? (
          <p className="text-sm text-n-400">Consultando a Meta…</p>
        ) : erro && !diag ? (
          <Card>
            <p className="text-sm text-danger">{erro}</p>
          </Card>
        ) : diag ? (
          <>
            <Cabecalho diag={diag} />
            {diag.canal !== "meta" && <AvisoCanalDemo />}
            <Roteiro diag={diag} />
            <Passos diag={diag} tenantId={tenantId} onMudou={atualizar} />
            <Conclusao tenantId={tenantId} onMudou={atualizar} />
          </>
        ) : null}
      </div>
    </AppShell>
  );
}

function Cabecalho({ diag }: { diag: DiagnosticoWhatsApp }) {
  const etapa = ETAPAS[diag.numero?.etapa ?? "ausente"] ?? ETAPAS.desconhecida;
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-n-900">{diag.escola}</h2>
          <p className="mt-1 text-xs text-n-500">
            {diag.numero?.numero_exibicao || "sem número"}
            {diag.conta_nome && ` · conta ${diag.conta_nome}`}
            {diag.meta_waba_id && ` (${diag.meta_waba_id})`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={etapa.tone} dot>
            {etapa.rotulo}
          </Badge>
          {diag.numero?.qualidade && (
            <Badge tone={diag.numero.qualidade === "GREEN" ? "success" : "warning"}>
              Qualidade {diag.numero.qualidade}
            </Badge>
          )}
          <Badge tone={diag.pronta ? "success" : "warning"}>
            {diag.pronta ? "Pronta para atender" : "Com pendências"}
          </Badge>
        </div>
      </div>
    </Card>
  );
}

function AvisoCanalDemo() {
  return (
    <Card className="border-danger/40 bg-danger-soft/40">
      <CardHeader title="O servidor está no canal demo" />
      <p className="text-xs text-n-600">
        Nada nesta tela foi conferido contra a Meta, e <strong>nenhuma mensagem chega ao
        responsável</strong> — o inbound é atendido, cobra LLM e a resposta se perde. Falta{" "}
        <code>META_ACCESS_TOKEN</code> ou <code>MESSAGE_CHANNEL=meta</code> no servidor.
        Resolva isso antes de qualquer passo abaixo.
      </p>
    </Card>
  );
}

/** O checklist: cada linha é um passo que já custou um dia de depuração. */
function Roteiro({ diag }: { diag: DiagnosticoWhatsApp }) {
  return (
    <Card>
      <CardHeader title="O que falta para esta escola atender" count={diag.passos.length} />
      <ul className="flex flex-col gap-2.5">
        {diag.passos.map((p) => (
          <li key={p.chave} className="flex items-start gap-2.5">
            <span
              className={
                "mt-0.5 flex h-4 w-4 flex-none items-center justify-center rounded-full text-[10px] font-bold text-white " +
                (p.concluido ? "bg-success" : p.manual ? "bg-accent" : "bg-danger")
              }
              aria-hidden
            >
              {p.concluido ? "✓" : "!"}
            </span>
            <div className="min-w-0">
              <p className="text-[13px] font-semibold text-n-800">{p.titulo}</p>
              {p.detalhe && <p className="mt-0.5 text-xs text-n-500">{p.detalhe}</p>}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** Os quatro passos executáveis, na única ordem que a Meta aceita. */
function Passos({
  diag,
  tenantId,
  onMudou,
}: {
  diag: DiagnosticoWhatsApp;
  tenantId: string;
  onMudou: () => Promise<void>;
}) {
  const etapa = diag.numero?.etapa ?? "ausente";
  if (!diag.numero) return <CadastroDoNumero tenantId={tenantId} onMudou={onMudou} />;
  if (etapa === "nao_verificado")
    return <Verificacao tenantId={tenantId} onMudou={onMudou} />;
  if (etapa === "nao_registrado")
    return <Inscricao tenantId={tenantId} onMudou={onMudou} />;
  return <NumeroPronto diag={diag} tenantId={tenantId} onMudou={onMudou} />;
}

function CadastroDoNumero({
  tenantId,
  onMudou,
}: {
  tenantId: string;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [numero, setNumero] = useState("");
  const [nome, setNome] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function cadastrar() {
    setSalvando(true);
    try {
      await cadastrarNumeroNaMeta(tenantId, numero, nome);
      await onMudou();
      toast({ tone: "success", title: "Número cadastrado na conta da escola." });
    } catch (e) {
      toast({ tone: "danger", title: e instanceof Error ? e.message : "Falha ao cadastrar." });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Card>
      <CardHeader title="1 · Cadastrar o número na Meta" />
      <div className="flex flex-col gap-3">
        <p className="text-xs text-n-500">
          O chip precisa ser <strong>novo e dedicado</strong>: não pode estar ativo em nenhum
          WhatsApp (comum ou Business) neste momento, e depois de registrado na Cloud API
          <strong> não volta</strong> a funcionar no aplicativo.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Número do chip (E.164)" htmlFor="numero">
            <Input
              id="numero"
              mono
              placeholder="+5515997536978"
              value={numero}
              onChange={(e) => setNumero(e.target.value)}
            />
          </Field>
          <Field
            label="Nome de exibição"
            htmlFor="nome"
            hint="O que os pais veem. Vazio = nome da escola. Passa por revisão da Meta."
          >
            <Input
              id="nome"
              placeholder="EM Rosa Cury"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
            />
          </Field>
        </div>
        <div>
          <Button size="sm" onClick={cadastrar} disabled={salvando || !numero.trim()}>
            {salvando ? "Cadastrando…" : "Cadastrar na conta da escola"}
          </Button>
        </div>
      </div>
    </Card>
  );
}

function Verificacao({ tenantId, onMudou }: { tenantId: string; onMudou: () => Promise<void> }) {
  const toast = useToast();
  const [metodo, setMetodo] = useState<"SMS" | "VOICE">("SMS");
  const [codigo, setCodigo] = useState("");
  const [ocupado, setOcupado] = useState(false);

  async function pedir() {
    setOcupado(true);
    try {
      await pedirCodigoDeVerificacao(tenantId, metodo);
      toast({
        tone: "success",
        title: `Código pedido por ${metodo === "SMS" ? "SMS" : "ligação"}.`,
        description: "Se não chegar, espere algumas horas antes de tentar de novo.",
      });
    } catch (e) {
      toast({ tone: "danger", title: e instanceof Error ? e.message : "Falha ao pedir o código." });
    } finally {
      setOcupado(false);
    }
  }

  async function confirmar() {
    setOcupado(true);
    try {
      await confirmarCodigoDeVerificacao(tenantId, codigo);
      await onMudou();
      toast({ tone: "success", title: "Número verificado. Falta inscrevê-lo." });
    } catch (e) {
      toast({ tone: "danger", title: e instanceof Error ? e.message : "Código recusado." });
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Card>
      <CardHeader title="2 · Verificar o número" />
      <div className="flex flex-col gap-3">
        <p className="text-xs text-n-500">
          O código de 6 dígitos vai para o chip, que está com a gente — a escola não
          participa. <strong>Não insista:</strong> a Meta trava a verificação por horas
          depois de alguns reenvios falhos, e é justamente a tentativa seguinte que se
          perde. Duas falhas ⇒ esperar, não trocar de chip.
        </p>
        <div className="grid gap-3 sm:grid-cols-[160px_1fr]">
          <Field label="Método" htmlFor="metodo">
            <Select
              id="metodo"
              value={metodo}
              onChange={(e) => setMetodo(e.target.value as "SMS" | "VOICE")}
            >
              <option value="SMS">SMS</option>
              <option value="VOICE">Ligação</option>
            </Select>
          </Field>
          <Field label="Código recebido" htmlFor="codigo">
            <Input
              id="codigo"
              mono
              inputMode="numeric"
              maxLength={6}
              placeholder="123456"
              value={codigo}
              onChange={(e) => setCodigo(e.target.value)}
            />
          </Field>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" onClick={pedir} disabled={ocupado}>
            {ocupado ? "Aguarde…" : "Pedir código"}
          </Button>
          <Button size="sm" onClick={confirmar} disabled={ocupado || codigo.trim().length !== 6}>
            Confirmar código
          </Button>
        </div>
      </div>
    </Card>
  );
}

function Inscricao({ tenantId, onMudou }: { tenantId: string; onMudou: () => Promise<void> }) {
  const toast = useToast();
  const [pin, setPin] = useState("");
  const [ocupado, setOcupado] = useState(false);

  async function inscrever() {
    setOcupado(true);
    try {
      await inscreverNumeroNaCloudApi(tenantId, pin);
      await onMudou();
      toast({ tone: "success", title: "Número inscrito na Cloud API." });
    } catch (e) {
      toast({ tone: "danger", title: e instanceof Error ? e.message : "Falha ao inscrever." });
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Card>
      <CardHeader title="3 · Inscrever na Cloud API" />
      <div className="flex flex-col gap-3">
        <p className="text-xs text-n-500">
          <strong>Verificar não é registrar:</strong> o número está verificado e ainda mudo.
          Escolha um PIN de 6 dígitos (verificação em duas etapas) e{" "}
          <strong>guarde-o no gerenciador de senhas</strong> — a Meta o exige de novo para
          reinscrever o número no futuro e não o exibe outra vez. Nós não o guardamos.
        </p>
        <div className="sm:max-w-[220px]">
          <Field label="PIN de 6 dígitos" htmlFor="pin">
            <Input
              id="pin"
              mono
              inputMode="numeric"
              maxLength={6}
              placeholder="000000"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
            />
          </Field>
        </div>
        <div>
          <Button size="sm" onClick={inscrever} disabled={ocupado || pin.trim().length !== 6}>
            {ocupado ? "Inscrevendo…" : "Inscrever número"}
          </Button>
        </div>
      </div>
    </Card>
  );
}

function NumeroPronto({
  diag,
  tenantId,
  onMudou,
}: {
  diag: DiagnosticoWhatsApp;
  tenantId: string;
  onMudou: () => Promise<void>;
}) {
  const toast = useToast();
  const [confirmando, setConfirmando] = useState(false);

  async function desvincular() {
    try {
      await desvincularNumeroDaEscola(tenantId);
      setConfirmando(false);
      await onMudou();
      toast({ tone: "success", title: "Número desvinculado desta escola." });
    } catch (e) {
      toast({ tone: "danger", title: e instanceof Error ? e.message : "Falha ao desvincular." });
    }
  }

  return (
    <>
      <Card>
        <CardHeader title="Número em operação" />
        <dl className="grid gap-3 text-xs sm:grid-cols-3">
          <div>
            <dt className="font-semibold text-n-600">phone_number_id</dt>
            <dd className="font-mono text-n-800">{diag.numero?.phone_number_id}</dd>
          </div>
          <div>
            <dt className="font-semibold text-n-600">Nome de exibição</dt>
            <dd className="text-n-800">
              {diag.numero?.nome_exibicao} ({diag.numero?.status_nome || "—"})
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-n-600">Estado na Meta</dt>
            <dd className="font-mono text-n-800">{diag.numero?.bruto}</dd>
          </div>
        </dl>
        <p className="mt-3 text-xs text-n-400">
          Desvincular solta o número <strong>desta escola</strong> e não mexe na Meta: o
          número continua registrado. Serve para corrigir um id cadastrado na escola errada.
        </p>
        <div className="mt-2">
          <Button size="sm" variant="secondary" onClick={() => setConfirmando(true)}>
            Desvincular da escola
          </Button>
        </div>
      </Card>
      <ConfirmDialog
        open={confirmando}
        title="Desvincular o número desta escola?"
        message="A escola deixa de receber e enviar mensagens até que outro número seja vinculado. O número continua registrado na Meta."
        confirmLabel="Desvincular"
        onConfirm={desvincular}
        onClose={() => setConfirmando(false)}
      />
    </>
  );
}

/** Os dois passos que não têm tela no console da Meta — e por isso somem do roteiro. */
function Conclusao({ tenantId, onMudou }: { tenantId: string; onMudou: () => Promise<void> }) {
  const toast = useToast();
  const [rodando, setRodando] = useState(false);

  async function concluir() {
    setRodando(true);
    try {
      const r = await concluirOnboarding(tenantId);
      await onMudou();
      toast({
        tone: r.avisos.length > 0 ? "danger" : "success",
        title: r.conta_inscrita_no_app
          ? `Conta inscrita no app · ${r.templates_submetidos} template(s) submetido(s).`
          : "Conclusão executada com pendências.",
        description: r.avisos.length > 0 ? r.avisos.join(" · ") : undefined,
      });
    } catch (e) {
      toast({ tone: "danger", title: e instanceof Error ? e.message : "Falha ao concluir." });
    } finally {
      setRodando(false);
    }
  }

  return (
    <Card>
      <CardHeader title="4 · Conferir e completar" />
      <div className="flex flex-col gap-3">
        <p className="text-xs text-n-500">
          Dois passos <strong>sem interface no console da Meta</strong>, e sem os quais a
          escola nasce quebrada em silêncio:
        </p>
        <ul className="ml-4 list-disc text-xs text-n-500">
          <li>
            <strong>Inscrever a conta no app</strong> (<code>subscribed_apps</code>). Faltando,
            a Meta não envia evento nenhum e não reporta erro: console verde, número
            conectado, webhook mudo.
          </li>
          <li>
            <strong>Replicar os templates globais</strong> na conta. Aprovação é por conta —
            um <code>aviso_geral</code> aprovado em outra não existe nesta, e o disparo fora
            da janela de 24h é recusado.
          </li>
        </ul>
        <p className="text-xs text-n-400">
          É seguro repetir: as duas chamadas são idempotentes.
        </p>
        <div>
          <Button size="sm" onClick={concluir} disabled={rodando}>
            {rodando ? "Executando…" : "Conferir e completar"}
          </Button>
        </div>
      </div>
    </Card>
  );
}
