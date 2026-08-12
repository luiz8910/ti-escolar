"use client";

import { useEffect, useState, type ReactNode } from "react";
import { getEscolaEmFoco, getSessao } from "@/lib/admin";
import { Sidebar } from "./Sidebar";
import { Topbar, type TopbarUser } from "./Topbar";

/**
 * Casca do painel admin: Sidebar + Topbar + área de conteúdo rolável.
 * Reaproveite em todas as páginas de /admin.
 *
 *   <AppShell title="Grupos & disparos" user={user} isSuperAdmin={superAdmin}>
 *     ...conteúdo...
 *   </AppShell>
 *
 * O nome da escola **não é mais passado pelas páginas**: cada uma cravava
 * `tenantName="Escola Demonstração"`, de modo que toda escola via o nome da escola de
 * demonstração na barra lateral. Agora a casca resolve sozinha — do login, para o admin
 * de escola; da escola em foco, para o super admin.
 *
 * No mobile a Sidebar vira um drawer off-canvas: fica escondida e abre pelo
 * botão de menu (hambúrguer) na Topbar. A partir de `lg` ela é fixa à esquerda.
 */
export function AppShell({
  title,
  user,
  isSuperAdmin = false,
  exigeEscola = true,
  onLogout,
  children,
}: {
  title: ReactNode;
  user: TopbarUser;
  isSuperAdmin?: boolean;
  /**
   * A tela opera sobre uma escola? Verdadeiro para quase tudo. As telas da plataforma
   * (escolas, segurança, logs) passam `false` — elas são cross-tenant e não devem exigir
   * uma escola em foco.
   */
  exigeEscola?: boolean;
  onLogout?: () => void;
  children: ReactNode;
}) {
  const [menuAberto, setMenuAberto] = useState(false);
  const [escola, setEscola] = useState("");
  const [semEscola, setSemEscola] = useState(false);
  const [pronto, setPronto] = useState(false);

  // Em efeito, não no render: `localStorage` não existe no servidor, e ler direto no
  // corpo do componente daria divergência de hidratação.
  useEffect(() => {
    const sessao = getSessao();
    const foco = getEscolaEmFoco();
    setEscola(
      isSuperAdmin
        ? (foco?.nome ?? "Nenhuma escola selecionada")
        : (sessao?.usuario.tenant_nome ?? ""),
    );
    setSemEscola(isSuperAdmin && !foco);
    setPronto(true);
  }, [isSuperAdmin]);

  return (
    <div className="flex min-h-screen bg-bg">
      <Sidebar
        subtitle={escola}
        isSuperAdmin={isSuperAdmin}
        open={menuAberto}
        onClose={() => setMenuAberto(false)}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          title={title}
          user={user}
          showTenant={isSuperAdmin}
          onLogout={onLogout}
          onMenu={() => setMenuAberto(true)}
        />
        <main className="flex-1 overflow-y-auto p-4 sm:p-6">
          {/* Super admin sem escola escolhida: a tela pede a escolha em vez de operar
              sobre uma escola arbitrária. Antes o painel caía no tenant de demonstração
              sem avisar ninguém — editando a escola errada em silêncio. */}
          {pronto && exigeEscola && semEscola ? <EscolhaUmaEscola /> : children}
        </main>
      </div>
    </div>
  );
}

function EscolhaUmaEscola() {
  return (
    <div className="mx-auto mt-10 max-w-lg rounded-xl border border-n-200 bg-white p-7 text-center">
      <h2 className="text-lg font-bold tracking-tight text-n-900">
        Escolha a escola em que deseja operar
      </h2>
      <p className="mt-2 text-sm text-n-500">
        Esta tela age sobre os dados de <b>uma escola</b>. Como você é super admin, precisa
        dizer qual — use o seletor no topo da página, ou entre pela lista de{" "}
        <a href="/admin/escolas" className="font-semibold text-brand-600 hover:underline">
          Escolas
        </a>
        .
      </p>
    </div>
  );
}
