// Cliente da API do back-end TI-Escolar.

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Tenant fixo do seed de demonstração (Escola Demonstração).
export const DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001";

export interface DocumentoSaida {
  nome: string;
  categoria: string;
  url: string;
}

export interface MensagemSaida {
  texto: string;
  fontes: string[];
  documentos: DocumentoSaida[];
}

export async function enviarMensagem(
  contato: string,
  texto: string
): Promise<MensagemSaida> {
  const resp = await fetch(`${API_URL}/api/chat/mensagens`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenant_id: DEMO_TENANT_ID, contato, texto }),
  });
  if (!resp.ok) {
    throw new Error(`Erro ${resp.status} ao enviar mensagem`);
  }
  return resp.json();
}
