"use client";

import { useState, type ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { Topbar, type TopbarUser } from "./Topbar";

/**
 * Casca do painel admin: Sidebar + Topbar + área de conteúdo rolável.
 * Reaproveite em todas as páginas de /admin.
 *
 *   <AppShell title="Grupos & disparos" user={user} tenantName="Escola Demonstração"
 *             isSuperAdmin={user.papel === "super_admin"}>
 *     ...conteúdo...
 *   </AppShell>
 *
 * No mobile a Sidebar vira um drawer off-canvas: fica escondida e abre pelo
 * botão de menu (hambúrguer) na Topbar. A partir de `lg` ela é fixa à esquerda.
 */
export function AppShell({
  title,
  user,
  tenantName,
  isSuperAdmin = false,
  onLogout,
  children,
}: {
  title: ReactNode;
  user: TopbarUser;
  tenantName?: string;
  isSuperAdmin?: boolean;
  onLogout?: () => void;
  children: ReactNode;
}) {
  const [menuAberto, setMenuAberto] = useState(false);

  return (
    <div className="flex min-h-screen bg-bg">
      <Sidebar
        subtitle={tenantName}
        isSuperAdmin={isSuperAdmin}
        open={menuAberto}
        onClose={() => setMenuAberto(false)}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          title={title}
          user={user}
          tenantName={tenantName}
          showTenant={isSuperAdmin}
          onLogout={onLogout}
          onMenu={() => setMenuAberto(true)}
        />
        <main className="flex-1 overflow-y-auto p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
