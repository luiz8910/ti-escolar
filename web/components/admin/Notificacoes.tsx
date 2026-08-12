"use client";

/**
 * Central de notificações do painel — o sininho que **não** era um sininho.
 *
 * O botão existia na `Topbar` sem `onClick`, com a bolinha vermelha cravada no JSX: ele
 * avisava sempre, inclusive com a fila zerada. Um alerta que está sempre aceso é um alerta
 * que ninguém olha.
 *
 * Duas fontes hoje — responsáveis esperando na fila (§6j) e documentos a conferir (§6k) —,
 * consolidadas num hook só. O polling que estava solto na `Sidebar` mudou para cá; o badge
 * do menu passou a ler daqui, então há **uma requisição** por ciclo, não uma por lugar que
 * mostra número.
 *
 * O **alerta em tela** dispara só quando a contagem *sobe* com a aba aberta. Só na
 * transição: um toast que reaparece a cada polling vira ruído, e a secretaria aprende a
 * ignorar — que é o oposto do que o apontamento pediu.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  contarAtendimentosPendentes,
  contarDocumentosPendentes,
  exigeEscolhaDeEscola,
  getSessao,
} from "@/lib/admin";
import { useToast } from "@/components/ui/Toast";
import { BellIcon, ChatBubbleIcon, FileIcon } from "@/components/ui/icons";
import { cn } from "@/components/ui/cn";

/** De quanto em quanto tempo as fontes são reconferidas. */
const INTERVALO_MS = 20_000;

export interface Pendencias {
  atendimentos: number;
  documentos: number;
  total: number;
}

const VAZIO: Pendencias = { atendimentos: 0, documentos: 0, total: 0 };

/**
 * Contadores das fontes de notificação, com alerta na subida.
 *
 * Falha silenciosa de propósito: um contador que não atualizou não justifica um toast de
 * erro atravessando o painel de quem está no meio de um atendimento.
 */
export function usePendencias(): Pendencias {
  const [pendencias, setPendencias] = useState<Pendencias>(VAZIO);
  const anterior = useRef<Pendencias | null>(null);
  const toast = useToast();

  const conferir = useCallback(async () => {
    // Sem sessão (logout no meio do intervalo) ou sem escola escolhida (super admin), nem
    // tenta: a chamada dispararia redirecionamento ou exceção por causa de um badge.
    if (!getSessao() || exigeEscolhaDeEscola()) return;
    const [atendimentos, documentos] = await Promise.all([
      contarAtendimentosPendentes().catch(() => anterior.current?.atendimentos ?? 0),
      contarDocumentosPendentes().catch(() => anterior.current?.documentos ?? 0),
    ]);
    const atual: Pendencias = {
      atendimentos,
      documentos,
      total: atendimentos + documentos,
    };

    const antes = anterior.current;
    // Só na transição, e só depois da primeira leitura: avisar no carregamento faria a
    // tela gritar sobre coisa que já estava lá quando a pessoa abriu o painel.
    if (antes) {
      if (atendimentos > antes.atendimentos) {
        toast({
          tone: "info",
          title: "Novo atendimento na fila",
          description: "Um responsável está esperando falar com a secretaria.",
        });
      }
      if (documentos > antes.documentos) {
        toast({
          tone: "info",
          title: "Novo documento recebido",
          description: "Um responsável enviou um arquivo pelo WhatsApp.",
        });
      }
    }
    anterior.current = atual;
    setPendencias(atual);
  }, [toast]);

  useEffect(() => {
    let vivo = true;
    const rodar = () => {
      if (document.hidden) return; // aba escondida não gera requisição por nada
      conferir().catch(() => undefined);
    };
    rodar();
    const timer = setInterval(() => vivo && rodar(), INTERVALO_MS);
    // Voltar para a aba reconfere na hora: esperar até 20s depois de trazer o painel de
    // volta é o intervalo em que a pessoa está justamente olhando.
    document.addEventListener("visibilitychange", rodar);
    return () => {
      vivo = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", rodar);
    };
  }, [conferir]);

  return pendencias;
}

export function SininhoNotificacoes({ pendencias }: { pendencias: Pendencias }) {
  const router = useRouter();
  const [aberto, setAberto] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => {
      if (caixa.current && !caixa.current.contains(e.target as Node)) setAberto(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setAberto(false);
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", esc);
    };
  }, [aberto]);

  const itens = [
    {
      chave: "atendimentos",
      icone: <ChatBubbleIcon size={16} />,
      total: pendencias.atendimentos,
      titulo: "responsável esperando",
      titulos: "responsáveis esperando",
      destino: "/admin/atendimentos",
    },
    {
      chave: "documentos",
      icone: <FileIcon size={16} />,
      total: pendencias.documentos,
      titulo: "documento a conferir",
      titulos: "documentos a conferir",
      destino: "/admin/documentos",
    },
  ].filter((i) => i.total > 0);

  return (
    <div className="relative" ref={caixa}>
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        aria-label={
          pendencias.total
            ? `Notificações (${pendencias.total} pendente(s))`
            : "Notificações"
        }
        aria-expanded={aberto}
        className="relative flex h-9 w-9 items-center justify-center rounded-[10px] border border-n-100 text-n-500 hover:bg-n-50"
      >
        <BellIcon size={18} />
        {/* A bolinha só acende com pendência — antes era fixa no JSX e avisava sempre. */}
        {pendencias.total > 0 && (
          <span className="absolute right-1 top-1 min-w-[16px] rounded-full border-[1.5px] border-white bg-danger px-[3px] text-center text-[9px] font-bold leading-[13px] text-white">
            {pendencias.total > 9 ? "9+" : pendencias.total}
          </span>
        )}
      </button>

      {aberto && (
        <div className="absolute right-0 z-40 mt-1.5 w-[260px] rounded-xl border border-n-200 bg-white p-1.5 shadow-lg">
          <p className="px-2.5 py-1.5 text-[10px] font-bold tracking-[0.1em] text-n-400">
            PRECISAM DE VOCÊ
          </p>
          {itens.map((i) => (
            <button
              key={i.chave}
              onClick={() => {
                setAberto(false);
                router.push(i.destino);
              }}
              className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-medium text-n-700 hover:bg-n-50"
            >
              <span className="text-brand-600">{i.icone}</span>
              <span className="flex-1">
                <b>{i.total}</b> {i.total === 1 ? i.titulo : i.titulos}
              </span>
            </button>
          ))}
          {itens.length === 0 && (
            <p className="px-2.5 py-3 text-[12.5px] text-n-400">
              Nada pendente. Você está em dia.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** Badge de contagem reaproveitado pelo menu lateral. */
export function BadgeContador({ total }: { total: number }) {
  if (!total) return null;
  return (
    <span
      className={cn(
        "ml-auto min-w-[20px] rounded-full bg-danger px-1.5 py-0.5",
        "text-center text-[10px] font-bold text-white",
      )}
    >
      {total > 99 ? "99+" : total}
    </span>
  );
}
