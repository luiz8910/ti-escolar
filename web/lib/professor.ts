// Cliente da API do professor (mural) + sessão JWT própria em localStorage.
// Separado do painel administrativo: token com papel "professor".

import { API_URL, DEMO_TENANT_ID } from "./api";

const STORAGE_KEY = "tiescolar.professor";

export interface ProfessorLogado {
  id: string;
  nome: string;
  telefone: string;
  tenant_id: string;
}

interface SessaoProfessor {
  professor: ProfessorLogado;
  token: string;
  expiraEm: number;
}

export interface RecadoDoProfessor {
  id: string;
  titulo: string;
  corpo: string;
  autor_nome: string;
  criado_em: string;
  lido: boolean;
  lido_em: string | null;
}

export interface ImpressaoProfessor {
  id: string;
  arquivo_nome: string;
  copias: number;
  colorido: boolean;
  frente_verso: boolean;
  status: string;
  criado_em: string;
}

export function getSessaoProfessor(): SessaoProfessor | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  const s = JSON.parse(raw) as SessaoProfessor;
  if (s.expiraEm && Date.now() >= s.expiraEm) {
    window.localStorage.removeItem(STORAGE_KEY);
    return null;
  }
  return s;
}

export function logoutProfessor() {
  window.localStorage.removeItem(STORAGE_KEY);
}

function authHeaders(): Record<string, string> {
  const s = getSessaoProfessor();
  if (!s) {
    logoutProfessor();
    if (typeof window !== "undefined") window.location.replace("/professor/login");
    throw new Error("Sessão expirada");
  }
  return { Authorization: `Bearer ${s.token}` };
}

async function jsonOuErro<T>(resp: Response, contexto: string): Promise<T> {
  if (!resp.ok) {
    const erro = await resp.json().catch(() => ({}));
    throw new Error(erro.detail ?? `Erro ${resp.status} ao ${contexto}`);
  }
  return resp.json() as Promise<T>;
}

// tenant do professor: no demo, o tenant fixo; em produção viria da URL/config.
export function tenantProfessor(): string {
  return DEMO_TENANT_ID;
}

export async function loginProfessor(
  telefone: string,
  senha: string,
  tenantId: string = tenantProfessor()
): Promise<ProfessorLogado> {
  const resp = await fetch(`${API_URL}/api/professor/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenant_id: tenantId, telefone, senha }),
  });
  if (!resp.ok) throw new Error("Telefone ou senha inválidos");
  const dados = (await resp.json()) as {
    access_token: string;
    expira_em: number;
    professor: ProfessorLogado;
  };
  window.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      professor: dados.professor,
      token: dados.access_token,
      expiraEm: Date.now() + dados.expira_em * 1000,
    })
  );
  return dados.professor;
}

export async function meusRecados(): Promise<RecadoDoProfessor[]> {
  const resp = await fetch(`${API_URL}/api/professor/recados`, { headers: authHeaders() });
  return jsonOuErro(resp, "carregar recados");
}

export async function confirmarLeitura(recadoId: string): Promise<void> {
  const resp = await fetch(`${API_URL}/api/professor/recados/${recadoId}/leitura`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!resp.ok && resp.status !== 204) throw new Error("Falha ao confirmar leitura");
}

export async function solicitarImpressaoProfessor(dados: {
  arquivo_nome: string;
  copias: number;
  colorido: boolean;
  frente_verso: boolean;
  observacao?: string;
}): Promise<ImpressaoProfessor> {
  const resp = await fetch(`${API_URL}/api/professor/impressao`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(dados),
  });
  return jsonOuErro(resp, "enviar para impressão");
}
