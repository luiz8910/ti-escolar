import { redirect } from "next/navigation";

// A raiz era o simulador do WhatsApp, removido quando o canal real entrou no ar. Redireciona
// em vez de devolver 404: `/` é o que fica salvo nos favoritos e é o que a Vercel serve no
// domínio nu — quem chega aqui quer o painel.
export default function Page() {
  redirect("/admin");
}
