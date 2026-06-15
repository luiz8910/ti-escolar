// Cliente da API administrativa + sessão simples (credenciais em localStorage).
//
// A autenticação do back-end (scaffold) é por cabeçalhos X-User-Email / X-User-Senha.
// Guardamos essas credenciais após o login e as reenviamos em cada chamada admin.

import { API_URL, DEMO_TENANT_ID } from "./api";

// Template aprovado criado pelo seed (usado nos disparos do painel).
export const DEMO_TEMPLATE_ID = "00000000-0000-0000-0000-0000000000a1";

const STORAGE_KEY = "tiescolar.admin";

export interface Usuario {
  id: string;
  nome: string;
  email: string;
  papel: "super_admin" | "tenant_admin";
  tenant_id: string | null;
}

interface Sessao {
  usuario: Usuario;
  email: string;
  senha: string;
}

export interface Contato {
  id: string;
  nome: string;
  telefone: string;
}

export interface Grupo {
  id: string;
  nome: string;
  descricao: string;
  total_membros: number;
  membros: Contato[];
}

export interface Quota {
  tenant_id: string;
  dia: string;
  limite_diario: number;
  enviados: number;
  restante: number;
}

export interface ResultadoEnvioGrupo {
  grupo_id: string;
  total_contatos: number;
  broadcast: {
    broadcast_id: string;
    status: string;
    enviados: number;
    falhas: number;
    bloqueados_por_limite: number;
    restante_cota: number;
  };
}

// --------------------------- sessão --------------------------------------- //
export function getSessao(): Sessao | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  return raw ? (JSON.parse(raw) as Sessao) : null;
}

function setSessao(s: Sessao) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
}

export function logout() {
  window.localStorage.removeItem(STORAGE_KEY);
}

function authHeaders(): Record<string, string> {
  const s = getSessao();
  if (!s) throw new Error("Sessão expirada");
  return { "X-User-Email": s.email, "X-User-Senha": s.senha };
}

// O tenant em foco: super admin opera sobre o tenant demo; admin usa o seu.
export function tenantEmFoco(): string {
  const s = getSessao();
  return s?.usuario.tenant_id ?? DEMO_TENANT_ID;
}

// --------------------------- chamadas ------------------------------------- //
export async function login(email: string, senha: string): Promise<Usuario> {
  const resp = await fetch(`${API_URL}/api/admin/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, senha }),
  });
  if (!resp.ok) throw new Error("Credenciais inválidas");
  const usuario = (await resp.json()) as Usuario;
  setSessao({ usuario, email, senha });
  return usuario;
}

export async function listarGrupos(): Promise<Grupo[]> {
  const resp = await fetch(`${API_URL}/api/admin/grupos/${tenantEmFoco()}`, {
    headers: authHeaders(),
  });
  if (!resp.ok) throw new Error(`Erro ${resp.status} ao listar grupos`);
  return resp.json();
}

export async function criarGrupo(nome: string, descricao: string): Promise<Grupo> {
  const resp = await fetch(`${API_URL}/api/admin/grupos`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), nome, descricao }),
  });
  if (!resp.ok) throw new Error(`Erro ${resp.status} ao criar grupo`);
  return resp.json();
}

export async function adicionarContato(
  grupoId: string,
  nome: string,
  telefone: string
): Promise<Contato> {
  const resp = await fetch(`${API_URL}/api/admin/grupos/${grupoId}/contatos`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), nome, telefone }),
  });
  if (!resp.ok) {
    const erro = await resp.json().catch(() => ({}));
    throw new Error(erro.detail ?? `Erro ${resp.status} ao adicionar contato`);
  }
  return resp.json();
}

export async function enviarParaGrupo(
  grupoId: string,
  titulo: string,
  mensagem: string
): Promise<ResultadoEnvioGrupo> {
  const resp = await fetch(`${API_URL}/api/admin/grupos/${grupoId}/enviar`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      tenant_id: tenantEmFoco(),
      template_id: DEMO_TEMPLATE_ID,
      titulo,
      mensagem,
    }),
  });
  if (!resp.ok) {
    const erro = await resp.json().catch(() => ({}));
    throw new Error(erro.detail ?? `Erro ${resp.status} ao enviar`);
  }
  return resp.json();
}

export async function consultarQuota(): Promise<Quota> {
  const resp = await fetch(`${API_URL}/api/broadcasts/quota/${tenantEmFoco()}`, {
    headers: authHeaders(),
  });
  if (!resp.ok) throw new Error(`Erro ${resp.status} ao consultar cota`);
  return resp.json();
}
