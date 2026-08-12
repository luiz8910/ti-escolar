"use client";

/**
 * Postura de segurança — auditoria interna (super admin).
 *
 * Não é material de venda nem página para a escola: lista as medidas protetivas da
 * plataforma, o risco concreto que cada uma cobre e o status real no ambiente em execução.
 * O que ainda não existe aparece como PENDENTE, de propósito — um painel de auditoria que
 * escondesse a lacuna não serviria para auditar nada.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  getSessao,
  ItemChecklist,
  logout,
  MedidaSeguranca,
  obterPosturaSeguranca,
  PosturaSeguranca,
  StatusMedida,
  Usuario,
} from "@/lib/admin";

import { AppShell } from "@/components/layout/AppShell";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/components/ui/cn";
import { AlertIcon, CheckIcon, ExternalIcon, ShieldIcon } from "@/components/ui/icons";

const STATUS: Record<
  StatusMedida,
  { rotulo: string; tone: "success" | "warning" | "danger" | "neutral"; barra: string }
> = {
  ativa: { rotulo: "Ativa", tone: "success", barra: "bg-success" },
  atencao: { rotulo: "Atenção", tone: "warning", barra: "bg-accent" },
  pendente: { rotulo: "Pendente", tone: "danger", barra: "bg-danger" },
  nao_aplicavel: { rotulo: "Não se aplica", tone: "neutral", barra: "bg-n-300" },
};

// No checklist o rótulo "Ativa" não cabe — o item ou está atendido, ou não.
const STATUS_CHECKLIST: Record<StatusMedida, string> = {
  ativa: "Atendido",
  atencao: "Parcial",
  pendente: "Não atendido",
  nao_aplicavel: "Não se aplica",
};

function formatar(data: string): string {
  return new Date(data).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function SegurancaPage() {
  const router = useRouter();
  const toast = useToast();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [postura, setPostura] = useState<PosturaSeguranca | null>(null);
  const [carregando, setCarregando] = useState(true);

  const recarregar = useCallback(async () => {
    setPostura(await obterPosturaSeguranca());
  }, []);

  useEffect(() => {
    const s = getSessao();
    if (!s) {
      router.replace("/admin/login");
      return;
    }
    // Auditoria interna: o admin da escola não tem o que fazer aqui.
    if (s.usuario.papel !== "super_admin") {
      router.replace("/admin");
      return;
    }
    setUsuario(s.usuario);
    recarregar()
      .catch(() => toast({ tone: "danger", title: "Falha ao carregar a postura de segurança." }))
      .finally(() => setCarregando(false));
  }, [router, recarregar, toast]);

  function sair() {
    logout();
    router.replace("/admin/login");
  }

  if (!usuario) return null;

  // Agrupa preservando a ordem em que o back-end devolveu as categorias.
  const categorias: string[] = [];
  for (const m of postura?.medidas ?? []) {
    if (!categorias.includes(m.categoria)) categorias.push(m.categoria);
  }

  const alertasMedidas = (postura?.total_atencao ?? 0) + (postura?.total_pendentes ?? 0);
  const pendencias = alertasMedidas + (postura?.checklist_pendentes ?? 0);

  return (
    <AppShell
      exigeEscola={false}
      title="Segurança"
      user={{ name: usuario.nome, role: "Super Admin" }}
      isSuperAdmin
      onLogout={sair}
    >
      <div className="flex flex-col gap-[18px]">
        <div className="flex items-start gap-3 rounded-lg border border-brand-200 bg-brand-50 px-4 py-3.5 text-[13px] text-brand-900">
          <ShieldIcon size={18} className="mt-0.5 flex-none text-brand-600" />
          <p>
            Medidas protetivas da plataforma e o status de cada uma <b>no ambiente que está
            rodando agora</b>. Documento de <b>auditoria interna</b> — visível apenas para o super
            admin. Nenhum segredo é exibido: só se um segredo continua com o valor de exemplo.
          </p>
        </div>

        {carregando || !postura ? (
          <p className="text-sm text-n-400">Carregando…</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Tile rotulo="Ativas" valor={postura.total_ativas} tone="success" />
              <Tile rotulo="Atenção" valor={postura.total_atencao} tone="warning" />
              <Tile rotulo="Pendentes" valor={postura.total_pendentes} tone="danger" />
              <Card className="flex flex-col justify-center gap-1 py-3.5">
                <span className="text-[10.5px] font-bold uppercase tracking-[0.08em] text-n-400">
                  Ambiente
                </span>
                <span className="font-mono text-[13px] font-semibold text-n-900">
                  {postura.ambiente} · canal {postura.canal}
                </span>
              </Card>
            </div>

            <div
              className={cn(
                "flex items-start gap-3 rounded-lg border px-4 py-3.5 text-[13px]",
                postura.pronto_para_producao
                  ? "border-success/30 bg-success-soft text-success"
                  : "border-accent/40 bg-accent-soft text-[#92600a]",
              )}
            >
              {postura.pronto_para_producao ? (
                <CheckIcon size={18} className="mt-0.5 flex-none" />
              ) : (
                <AlertIcon size={18} className="mt-0.5 flex-none" />
              )}
              <p>
                {postura.pronto_para_producao ? (
                  <>Todas as medidas estão ativas e o checklist está atendido neste ambiente.</>
                ) : (
                  <>
                    <b>
                      {pendencias}{" "}
                      {pendencias === 1 ? "ponto exige" : "pontos exigem"} ação
                    </b>{" "}
                    antes de tratar este ambiente como produção — {alertasMedidas} nas medidas e{" "}
                    {postura.checklist_pendentes} no checklist. <b>Atenção</b> é o que existe no
                    código mas está desligado ou com configuração fraca; <b>Pendente</b> é o que
                    ainda não foi implementado.
                  </>
                )}
              </p>
            </div>

            <section className="flex flex-col gap-2.5">
              <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
                <h3 className="text-[10.5px] font-bold uppercase tracking-[0.12em] text-n-400">
                  Checklist de pré-deploy
                </h3>
                <span className="text-[11.5px] text-n-400">
                  {postura.checklist_ok} de {postura.checklist.length} atendidos ·{" "}
                  {postura.checklist_pendentes} exigem ação
                </span>
              </div>
              <Card className="p-0">
                <div className="flex flex-col">
                  {postura.checklist.map((item) => (
                    <ItemDoChecklist key={item.numero} item={item} />
                  ))}
                </div>
              </Card>
              {postura.checklist_fonte && (
                <a
                  href={postura.checklist_fonte}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 px-1 text-[11.5px] font-semibold text-brand-600 hover:underline"
                >
                  Conferir contra a lista de origem
                  <ExternalIcon size={12} />
                </a>
              )}
            </section>

            {categorias.map((categoria) => (
              <section key={categoria} className="flex flex-col gap-2.5">
                <h3 className="px-1 text-[10.5px] font-bold uppercase tracking-[0.12em] text-n-400">
                  {categoria}
                </h3>
                {postura.medidas
                  .filter((m) => m.categoria === categoria)
                  .map((m) => (
                    <Medida key={m.chave} medida={m} />
                  ))}
              </section>
            ))}

            <p className="px-1 text-[11.5px] text-n-400">
              Gerado em {formatar(postura.gerado_em)} · leitura direta da configuração em execução.
            </p>
          </>
        )}
      </div>
    </AppShell>
  );
}

function Tile({
  rotulo,
  valor,
  tone,
}: {
  rotulo: string;
  valor: number;
  tone: "success" | "warning" | "danger";
}) {
  const cor = {
    success: "text-success",
    warning: "text-[#92600a]",
    danger: "text-danger",
  }[tone];
  return (
    <Card className="flex flex-col justify-center gap-0.5 py-3.5">
      <span className="text-[10.5px] font-bold uppercase tracking-[0.08em] text-n-400">
        {rotulo}
      </span>
      <span className={cn("text-2xl font-extrabold leading-tight", valor === 0 ? "text-n-300" : cor)}>
        {valor}
      </span>
    </Card>
  );
}

function ItemDoChecklist({ item }: { item: ItemChecklist }) {
  const s = STATUS[item.status] ?? STATUS.pendente;
  return (
    <div className="border-t border-n-100 px-5 py-3.5 first:border-t-0">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-baseline gap-2.5">
          <span className="font-mono text-[11px] font-bold text-n-400">
            {String(item.numero).padStart(2, "0")}
          </span>
          <div>
            <h4 className="text-[13px] font-bold text-n-900">{item.titulo}</h4>
            <p className="mt-0.5 text-[12px] text-n-500">{item.exigencia}</p>
          </div>
        </div>
        <Badge tone={s.tone} dot={item.status !== "nao_aplicavel"}>
          {STATUS_CHECKLIST[item.status]}
        </Badge>
      </div>
      <p
        className={cn(
          "mt-2 text-[12.5px] leading-relaxed",
          item.status === "ativa" || item.status === "nao_aplicavel"
            ? "text-n-600"
            : "text-[#92600a]",
        )}
      >
        {item.situacao}
      </p>
    </div>
  );
}

function Medida({ medida }: { medida: MedidaSeguranca }) {
  const s = STATUS[medida.status] ?? STATUS.pendente;
  return (
    <Card className="relative overflow-hidden p-0">
      <span className={cn("absolute inset-y-0 left-0 w-[3px]", s.barra)} />
      <div className="flex flex-col gap-2 px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h4 className="text-[13.5px] font-bold text-n-900">{medida.titulo}</h4>
          <Badge tone={s.tone} dot>
            {s.rotulo}
          </Badge>
        </div>

        <p className="text-[13px] leading-relaxed text-n-600">{medida.descricao}</p>

        <div className="rounded-md bg-n-50 px-3 py-2.5">
          <span className="text-[10.5px] font-bold uppercase tracking-[0.08em] text-n-400">
            Risco que cobre
          </span>
          <p className="mt-1 text-[12.5px] leading-relaxed text-n-600">{medida.risco}</p>
        </div>

        {medida.detalhe && (
          <p
            className={cn(
              "text-[12.5px] leading-relaxed",
              medida.status === "ativa" ? "text-n-500" : "font-semibold text-[#92600a]",
            )}
          >
            {medida.detalhe}
          </p>
        )}

        {medida.referencia && (
          <span className="font-mono text-[10.5px] text-n-400">{medida.referencia}</span>
        )}
      </div>
    </Card>
  );
}
