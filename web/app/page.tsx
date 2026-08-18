"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/**
 * A raiz era o simulador do WhatsApp, removido quando o canal real entrou no ar.
 * Redireciona em vez de devolver 404: `/` é o que fica salvo nos favoritos.
 *
 * **Redireciona no cliente, e não com `redirect()` do servidor.** Com `output: "export"` não
 * existe servidor para executar o `redirect()`, e o Next gerava um `index.html` que era, na
 * prática, uma página de erro (`__next_error__`) — quem abrisse o domínio nu batia nela. O
 * defeito não aparecia em `next dev`, só na saída estática.
 *
 * Na Cloudflare Pages quem responde primeiro é o `public/_redirects`, que resolve no CDN
 * antes de carregar JS. Este componente é a rede de segurança para os hosts que não leem
 * aquele arquivo (a Vercel do homolog) e para quem chega com o cache antigo.
 */
export default function Page() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/admin");
  }, [router]);
  return null;
}
