import type { ReactNode } from "react";
import { BellIcon, ChevronDownIcon } from "../ui/icons";

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
  tenantName,
  showTenant = true,
  showBell = true,
  onLogout,
}: {
  title: ReactNode;
  user: TopbarUser;
  tenantName?: string;
  showTenant?: boolean;
  showBell?: boolean;
  onLogout?: () => void;
}) {
  return (
    <header className="flex h-[60px] flex-none items-center justify-between border-b border-n-100 bg-white px-6">
      <div className="text-base font-bold tracking-tight text-n-900">{title}</div>

      <div className="flex items-center gap-3.5">
        {showTenant && tenantName && (
          <button className="flex items-center gap-2 rounded-[10px] border border-n-100 bg-n-50 px-3 py-[7px]">
            <span className="h-[7px] w-[7px] rounded-full bg-brand-600" />
            <span className="text-[12.5px] font-semibold text-n-700">{tenantName}</span>
            <ChevronDownIcon size={13} className="text-n-400" />
          </button>
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
          <div className="flex h-[34px] w-[34px] items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-[13px] font-bold text-white">
            {initials(user.name)}
          </div>
          <div className="leading-tight">
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
