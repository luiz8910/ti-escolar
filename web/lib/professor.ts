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

// -------- A2/A4 · canal interno do professor para a secretaria/gestão -------- //
export type CategoriaSolicitacao = "secretaria" | "gestao" | "pedagogico";

export interface SolicitacaoInternaProfessor {
  id: string;
  assunto: string;
  corpo: string;
  categoria: CategoriaSolicitacao;
  status: "aberta" | "em_andamento" | "resolvida" | "cancelada";
  resposta: string;
  respondido_em: string | null;
  criado_em: string;
}

export async function minhasSolicitacoes(): Promise<SolicitacaoInternaProfessor[]> {
  const resp = await fetch(`${API_URL}/api/professor/solicitacoes`, {
    headers: authHeaders(),
  });
  return jsonOuErro(resp, "carregar solicitações");
}

export async function abrirSolicitacao(dados: {
  assunto: string;
  corpo: string;
  categoria: CategoriaSolicitacao;
}): Promise<SolicitacaoInternaProfessor> {
  const resp = await fetch(`${API_URL}/api/professor/solicitacoes`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(dados),
  });
  return jsonOuErro(resp, "abrir solicitação");
}

// -------- A3 · mensagens mediadas com os responsáveis (sem expor o nº) -------- //
export interface Interlocutor {
  contato_telefone: string;
  contato_nome: string;
  total_mensagens: number;
  ultima_em: string | null;
  ultima_previa: string;
}

export interface MensagemMediada {
  id: string;
  professor_id: string;
  contato_telefone: string;
  contato_nome: string;
  professor_nome: string;
  direcao: "responsavel_para_professor" | "professor_para_responsavel";
  corpo: string;
  criado_em: string;
}

export async function meusInterlocutores(): Promise<Interlocutor[]> {
  const resp = await fetch(`${API_URL}/api/professor/mensagens`, {
    headers: authHeaders(),
  });
  return jsonOuErro(resp, "carregar conversas");
}

export async function conversaComResponsavel(
  telefone: string
): Promise<MensagemMediada[]> {
  const resp = await fetch(
    `${API_URL}/api/professor/mensagens/${encodeURIComponent(telefone)}`,
    { headers: authHeaders() }
  );
  return jsonOuErro(resp, "carregar conversa");
}

export async function enviarAoResponsavel(
  telefone: string,
  corpo: string
): Promise<MensagemMediada> {
  const resp = await fetch(`${API_URL}/api/professor/mensagens`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ contato_telefone: telefone, corpo }),
  });
  return jsonOuErro(resp, "enviar mensagem");
}
