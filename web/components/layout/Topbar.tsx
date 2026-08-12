import type { ReactNode } from "react";
import { SeletorDeEscola } from "../admin/SeletorDeEscola";
import { BellIcon, MenuIcon } from "../ui/icons";

export interface TopbarUser {
  name: string;
  role: string; // ex.: "Admin da escola" | "Super Admin"
}

function initials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export function Topbar({
  title,
  user,
  showTenant = true,
  showBell = true,
  onLogout,
  onMenu,
}: {
  title: ReactNode;
  user: TopbarUser;
  /** Mostra o seletor de escola (só faz sentido para o super admin). */
  showTenant?: boolean;
  showBell?: boolean;
  onLogout?: () => void;
  /** Abre o drawer da Sidebar no mobile. */
  onMenu?: () => void;
}) {
  return (
    <header className="sticky top-0 z-20 flex h-[60px] flex-none items-center justify-between gap-2 border-b border-n-100 bg-white px-4 sm:px-6">
      <div className="flex min-w-0 items-center gap-2.5">
        {onMenu && (
          <button
            type="button"
            onClick={onMenu}
            aria-label="Abrir menu"
            className="-ml-1 flex h-9 w-9 flex-none items-center justify-center rounded-[10px] text-n-600 hover:bg-n-50 lg:hidden"
          >
            <MenuIcon size={20} />
          </button>
        )}
        <div className="truncate text-base font-bold tracking-tight text-n-900">{title}</div>
      </div>

      <div className="flex flex-none items-center gap-2 sm:gap-3.5">
        {/* Só o super admin escolhe escola; para o admin de tenant o seletor não
            renderiza (ele é amarrado à sua escola). `showTenant` já vinha ligado só para
            super admin — antes exibia um botão decorativo, sem ação nenhuma. */}
        {showTenant && (
          <div className="hidden md:block">
            <SeletorDeEscola />
          </div>
        )}

        {showBell && (
          <button
            aria-label="Notificações"
            className="relative flex h-9 w-9 items-center justify-center rounded-[10px] border border-n-100 text-n-500 hover:bg-n-50"
          >
            <BellIcon size={18} />
            <span className="absolute right-2 top-[7px] h-[7px] w-[7px] rounded-full border-[1.5px] border-white bg-accent" />
          </button>
        )}

        <div className="flex items-center gap-2.5 border-l border-n-100 pl-1.5">
          <div className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-[13px] font-bold text-white">
            {initials(user.name)}
          </div>
          <div className="hidden leading-tight sm:block">
            <div className="text-[13px] font-bold text-n-900">{user.name}</div>
            <div className="text-[11px] text-n-400">{user.role}</div>
          </div>
        </div>

        {onLogout && (
          <button
            onClick={onLogout}
            className="rounded-[10px] border border-n-100 px-3 py-[7px] text-[12.5px] font-semibold text-n-500 hover:bg-n-50 hover:text-n-700"
          >
            Sair
          </button>
        )}
      </div>
    </header>
  );
}
