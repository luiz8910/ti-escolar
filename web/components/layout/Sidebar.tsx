"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { cn } from "../ui/cn";
import {
  GridIcon,
  UsersIcon,
  BookIcon,
  InstructionsIcon,
  BuildingIcon,
  ChatBubbleIcon,
  ExternalIcon,
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
  { href: "/admin/conhecimento", label: "Base de conhecimento", icon: BookIcon },
  { href: "/admin/prompt", label: "Instruções da escola", icon: InstructionsIcon },
];

/** Marca TI-Escolar. */
function Brand({ subtitle }: { subtitle: string }) {
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
    </div>
  );
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
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
}: {
  subtitle?: string;
  isSuperAdmin?: boolean;
}) {
  const pathname = usePathname();
  const isActive = (href: string) =>
    href === "/admin" ? pathname === "/admin" : pathname.startsWith(href);

  return (
    <aside className="flex w-[236px] flex-none flex-col border-r border-n-100 bg-white">
      <Brand subtitle={isSuperAdmin ? "Plataforma · Super Admin" : subtitle} />

      <nav className="flex flex-1 flex-col gap-[3px] p-3">
        <div className="px-2.5 pb-2 pt-1.5 text-[10px] font-bold tracking-[0.12em] text-n-400">
          PRINCIPAL
        </div>
        {PRINCIPAL.map((item) => (
          <NavLink key={item.href} item={item} active={isActive(item.href)} />
        ))}

        {isSuperAdmin && (
          <>
            <div className="px-2.5 pb-2 pt-3.5 text-[10px] font-bold tracking-[0.12em] text-n-400">
              ADMINISTRAÇÃO
            </div>
            <NavLink
              item={{ href: "/admin/escolas", label: "Escolas", icon: BuildingIcon, badge: "super" }}
              active={isActive("/admin/escolas")}
            />
          </>
        )}
      </nav>

      <div className="border-t border-n-100 p-3">
        <Link
          href="/"
          className="flex items-center gap-3 rounded-[10px] bg-[#effbf8] px-[11px] py-2.5 text-[13px] font-semibold text-[#0d8a78] no-underline hover:bg-[#cdf3ea]"
        >
          <ChatBubbleIcon size={18} />
          Ver demo do chat
          <ExternalIcon size={14} className="ml-auto" />
        </Link>
      </div>
    </aside>
  );
}
