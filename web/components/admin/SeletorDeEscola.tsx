"use client";

/**
 * Seletor da **escola em foco** — só para o super admin.
 *
 * O admin de escola é amarrado ao seu tenant e não escolhe nada; para ele este
 * componente não renderiza. O super admin tem `tenant_id = NULL` e, desde que o seletor
 * saiu do painel, não tinha como dizer sobre qual escola estava operando: as telas de
 * escola caíam no tenant de demonstração **em silêncio**. Era o problema real por trás do
 * apontamento "Instruções da escola vai para super admin".
 *
 * A escolha é persistida ao lado da sessão e vale para todas as telas de escola.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Escola,
  getEscolaEmFoco,
  getSessao,
  listarEscolas,
  setEscolaEmFoco,
} from "@/lib/admin";
import { BuildingIcon, ChevronDownIcon } from "../ui/icons";
import { cn } from "../ui/cn";

export function SeletorDeEscola({ onTrocar }: { onTrocar?: () => void }) {
  const [aberto, setAberto] = useState(false);
  const [escolas, setEscolas] = useState<Escola[]>([]);
  const [foco, setFoco] = useState<string>("");
  const [nome, setNome] = useState<string>("");
  const caixa = useRef<HTMLDivElement>(null);

  const sessao = getSessao();
  const superAdmin = sessao?.usuario.papel === "super_admin";

  useEffect(() => {
    if (!superAdmin) return;
    const atual = getEscolaEmFoco();
    setFoco(atual?.tenantId ?? "");
    setNome(atual?.nome ?? "");
    listarEscolas()
      .then(setEscolas)
      .catch(() => undefined);
  }, [superAdmin]);

  // Fecha ao clicar fora e no Esc — é um popover, não um modal.
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

  const escolher = useCallback(
    (escola: Escola) => {
      setEscolaEmFoco({ tenantId: escola.id, nome: escola.nome });
      setFoco(escola.id);
      setNome(escola.nome);
      setAberto(false);
      // Recarrega para que toda a página releia `tenantEmFoco()`. Menos elegante que um
      // contexto global, e muito mais confiável: nenhuma tela fica com dados da escola
      // anterior porque esqueceu de refazer a busca.
      onTrocar ? onTrocar() : window.location.reload();
    },
    [onTrocar],
  );

  if (!superAdmin) return null;

  const semEscolha = !foco;

  return (
    <div className="relative" ref={caixa}>
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={aberto}
        className={cn(
          "flex items-center gap-2 rounded-[10px] border px-3 py-[7px]",
          semEscolha
            ? "border-accent/40 bg-accent-soft text-[#7a5208]"
            : "border-n-100 bg-n-50 text-n-700",
        )}
      >
        <BuildingIcon size={15} className={semEscolha ? "text-accent" : "text-brand-600"} />
        <span className="max-w-[180px] truncate text-[12.5px] font-semibold">
          {semEscolha ? "Escolher escola" : nome}
        </span>
        <ChevronDownIcon size={13} className="text-n-400" />
      </button>

      {aberto && (
        <div
          role="listbox"
          className="absolute right-0 z-40 mt-1.5 max-h-[340px] w-[280px] overflow-y-auto rounded-xl border border-n-200 bg-white p-1.5 shadow-lg"
        >
          <p className="px-2.5 py-1.5 text-[10px] font-bold tracking-[0.1em] text-n-400">
            OPERAR COMO
          </p>
          {escolas.map((e) => (
            <button
              key={e.id}
              role="option"
              aria-selected={e.id === foco}
              onClick={() => escolher(e)}
              className={cn(
                "flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[13px]",
                e.id === foco
                  ? "bg-brand-50 font-bold text-brand-700"
                  : "font-medium text-n-700 hover:bg-n-50",
              )}
            >
              <span className="min-w-0 flex-1 truncate">{e.nome}</span>
              {e.licenca && e.licenca.status !== "ativo" && (
                <span className="flex-none text-[10.5px] font-bold text-danger">
                  {e.licenca.status === "cancelado" ? "cancelada" : "bloqueada"}
                </span>
              )}
            </button>
          ))}
          {escolas.length === 0 && (
            <p className="px-2.5 py-2 text-[12.5px] text-n-400">Nenhuma escola cadastrada.</p>
          )}
        </div>
      )}
    </div>
  );
}
