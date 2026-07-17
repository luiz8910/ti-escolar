"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { cn } from "../ui/cn";
import {
  GridIcon,
  UsersIcon,
  CapIcon,
  TeacherIcon,
  BookIcon,
  InstructionsIcon,
  BuildingIcon,
  ChatBubbleIcon,
  BellIcon,
  FileIcon,
  ExternalIcon,
  CloseIcon,
  SparkIcon,
  PrintIcon,
} from "../ui/icons";

interface NavItem {
  href: string;
  label: string;
  icon: (p: { size?: number }) => ReactNode;
  badge?: string;
}

const PRINCIPAL: NavItem[] = [
  { href: "/admin", label: "Grupos & disparos", icon: GridIcon },
  { href: "/admin/salas", label: "Salas e pais", icon: UsersIcon },
  { href: "/admin/alunos", label: "Alunos", icon: CapIcon },
  { href: "/admin/progressao", label: "Progressão de série", icon: CapIcon },
  { href: "/admin/professores", label: "Professores", icon: TeacherIcon },
  { href: "/admin/conhecimento", label: "Base de conhecimento", icon: BookIcon },
  { href: "/admin/prompt", label: "Instruções da escola", icon: InstructionsIcon },
];

// Comunicação interna e atendimento (Onda 1 · Rosa Cury + Onda 2 · consolidação).
const COMUNICACAO: NavItem[] = [
  { href: "/admin/respostas-rapidas", label: "Respostas rápidas", icon: SparkIcon },
  { href: "/admin/avisos", label: "Avisos do dia", icon: BellIcon },
  { href: "/admin/mural", label: "Mural do professor", icon: TeacherIcon },
  { href: "/admin/solicitacoes", label: "Canal do professor", icon: ChatBubbleIcon },
  { href: "/admin/impressao", label: "Fila de impressão", icon: PrintIcon },
  { href: "/admin/impressao/relatorio", label: "Cotas & relatório", icon: FileIcon },
];

// Observabilidade / histórico da escola (conversas, disparos e auditoria).
const HISTORICO: NavItem[] = [
  { href: "/admin/historico/conversas", label: "Conversas", icon: ChatBubbleIcon },
  { href: "/admin/historico/disparos", label: "Mensagens em massa", icon: BellIcon },
  { href: "/admin/historico/auditoria", label: "Auditoria", icon: FileIcon },
];

/** Marca TI-Escolar. */
function Brand({ subtitle, onClose }: { subtitle: string; onClose?: () => void }) {
  return (
    <div className="flex items-center gap-3 border-b border-n-100 px-4 py-[17px]">
      <div className="flex h-8 w-8 flex-none items-center justify-center rounded-[9px] bg-brand-600 text-white">
        <ChatBubbleIcon size={17} />
      </div>
      <div className="leading-none">
        <div className="text-[14.5px] font-extrabold tracking-tight text-n-900">
          TI<span className="text-brand-600">·</span>Escolar
        </div>
        <div className="mt-[3px] text-[10.5px] font-medium text-n-400">{subtitle}</div>
      </div>
      <button
        type="button"
        onClick={onClose}
        aria-label="Fechar menu"
        className="ml-auto flex h-9 w-9 items-center justify-center rounded-[10px] text-n-500 hover:bg-n-50 lg:hidden"
      >
        <CloseIcon size={20} />
      </button>
    </div>
  );
}

function NavLink({
  item,
  active,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  onNavigate?: () => void;
}) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        "relative flex items-center gap-3 rounded-[10px] px-[11px] py-2.5 text-[13px] no-underline transition-colors",
        active
          ? "bg-brand-50 font-bold text-brand-700"
          : "font-semibold text-n-600 hover:bg-n-50 hover:text-n-900",
      )}
    >
      {active && (
        <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r-[3px] bg-brand-600" />
      )}
      <Icon size={18} />
      {item.label}
      {item.badge && (
        <span className="ml-auto rounded-[5px] bg-brand-100 px-1.5 py-0.5 text-[9.5px] font-bold text-brand-700">
          {item.badge}
        </span>
      )}
    </Link>
  );
}

export function Sidebar({
  subtitle = "Escola Demonstração",
  isSuperAdmin = false,
  open = false,
  onClose,
}: {
  subtitle?: string;
  isSuperAdmin?: boolean;
  /** Drawer aberto no mobile (sem efeito a partir de `lg`). */
  open?: boolean;
  onClose?: () => void;
}) {
  const pathname = usePathname();
  const isActive = (href: string) =>
    href === "/admin" ? pathname === "/admin" : pathname.startsWith(href);

  // Fecha o drawer com Esc e trava o scroll do body enquanto aberto (só mobile).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose?.();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  return (
    <>
      {/* Backdrop — apenas no mobile com o drawer aberto */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-n-900/40 lg:hidden"
          aria-hidden="true"
          onClick={onClose}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-[236px] flex-none flex-col border-r border-n-100 bg-white transition-transform duration-200",
          "lg:static lg:z-auto lg:translate-x-0",
          open ? "translate-x-0 shadow-lg" : "-translate-x-full",
        )}
      >
        <Brand subtitle={isSuperAdmin ? "Plataforma · Super Admin" : subtitle} onClose={onClose} />

        <nav className="flex flex-1 flex-col gap-[3px] overflow-y-auto p-3">
          <div className="px-2.5 pb-2 pt-1.5 text-[10px] font-bold tracking-[0.12em] text-n-400">
            PRINCIPAL
          </div>
          {PRINCIPAL.map((item) => (
            <NavLink key={item.href} item={item} active={isActive(item.href)} onNavigate={onClose} />
          ))}

          <div className="px-2.5 pb-2 pt-3.5 text-[10px] font-bold tracking-[0.12em] text-n-400">
            COMUNICAÇÃO
          </div>
          {COMUNICACAO.map((item) => (
            <NavLink key={item.href} item={item} active={isActive(item.href)} onNavigate={onClose} />
          ))}

          <div className="px-2.5 pb-2 pt-3.5 text-[10px] font-bold tracking-[0.12em] text-n-400">
            HISTÓRICO
          </div>
          {HISTORICO.map((item) => (
            <NavLink key={item.href} item={item} active={isActive(item.href)} onNavigate={onClose} />
          ))}

          {isSuperAdmin && (
            <>
              <div className="px-2.5 pb-2 pt-3.5 text-[10px] font-bold tracking-[0.12em] text-n-400">
                ADMINISTRAÇÃO
              </div>
              <NavLink
                item={{ href: "/admin/escolas", label: "Escolas", icon: BuildingIcon, badge: "super" }}
                active={isActive("/admin/escolas")}
                onNavigate={onClose}
              />
            </>
          )}
        </nav>

        <div className="border-t border-n-100 p-3">
          <Link
            href="/"
            onClick={onClose}
            className="flex items-center gap-3 rounded-[10px] bg-[#effbf8] px-[11px] py-2.5 text-[13px] font-semibold text-[#0d8a78] no-underline hover:bg-[#cdf3ea]"
          >
            <ChatBubbleIcon size={18} />
            Ver demo do chat
            <ExternalIcon size={14} className="ml-auto" />
          </Link>
        </div>
      </aside>
    </>
  );
}
