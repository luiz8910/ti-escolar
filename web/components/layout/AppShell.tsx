import type { ReactNode } from "react";
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
  return (
    <div className="flex min-h-screen bg-bg">
      <Sidebar subtitle={tenantName} isSuperAdmin={isSuperAdmin} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar title={title} user={user} tenantName={tenantName} onLogout={onLogout} />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
