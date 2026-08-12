"use client";

/**
 * Redirecionamento de `/admin/salas` para `/admin/turmas`.
 *
 * A seção passou a se chamar **Turmas** (o vocabulário que a escola usa; "sala" lá é o
 * espaço físico). A rota antiga fica de pé porque a secretaria guarda link em favorito e
 * o painel é o lugar onde ela trabalha o dia inteiro — um 404 aqui é atrito puro.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function SalasRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/admin/turmas");
  }, [router]);
  return null;
}
