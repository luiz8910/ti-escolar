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

export interface Escola {
  id: string;
  nome: string;
  slug: string;
  criado_em: string;
  total_conversas: number;
  total_contatos: number;
  total_broadcasts: number;
}

export interface ConversaResumo {
  id: string;
  contato: string;
  criado_em: string;
  total_mensagens: number;
  ultima_mensagem: string;
  ultima_em: string | null;
}

export interface MensagemConversa {
  id: string;
  autor: "usuario" | "bot";
  texto: string;
  fontes: string[];
  criado_em: string;
}

export interface ConversaDetalhe {
  id: string;
  contato: string;
  criado_em: string;
  mensagens: MensagemConversa[];
}

export interface BroadcastResumo {
  id: string;
  titulo: string;
  status: string;
  criado_em: string;
  agendado_para: string | null;
  total_destinatarios: number;
  por_status: Record<string, number>;
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
  return consultarQuotaDe(tenantEmFoco());
}

export async function consultarQuotaDe(tenantId: string): Promise<Quota> {
  const resp = await fetch(`${API_URL}/api/broadcasts/quota/${tenantId}`, {
    headers: authHeaders(),
  });
  if (!resp.ok) throw new Error(`Erro ${resp.status} ao consultar cota`);
  return resp.json();
}

<<<<<<< HEAD
// --------------------------- escolas (super admin) ------------------------- //
async function erroDe(resp: Response, padrao: string): Promise<Error> {
  const corpo = await resp.json().catch(() => ({}));
  return new Error(corpo.detail ?? padrao);
}

export async function listarEscolas(): Promise<Escola[]> {
  const resp = await fetch(`${API_URL}/api/admin/escolas`, { headers: authHeaders() });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao listar escolas`);
  return resp.json();
}

export async function obterEscola(id: string): Promise<Escola> {
  const resp = await fetch(`${API_URL}/api/admin/escolas/${id}`, { headers: authHeaders() });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao carregar escola`);
  return resp.json();
}

export async function criarEscola(nome: string, slug: string): Promise<Escola> {
  const resp = await fetch(`${API_URL}/api/admin/escolas`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ nome, slug }),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao criar escola`);
  return resp.json();
}

export async function atualizarEscola(
  id: string,
  nome: string,
  slug: string
): Promise<Escola> {
  const resp = await fetch(`${API_URL}/api/admin/escolas/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ nome, slug }),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao atualizar escola`);
  return resp.json();
}

export async function removerEscola(id: string): Promise<void> {
  const resp = await fetch(`${API_URL}/api/admin/escolas/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!resp.ok && resp.status !== 204) {
    throw await erroDe(resp, `Erro ${resp.status} ao remover escola`);
  }
}

// --------------------------- conversas e broadcasts ------------------------ //
export async function listarConversas(tenantId: string): Promise<ConversaResumo[]> {
  const resp = await fetch(`${API_URL}/api/admin/escolas/${tenantId}/conversas`, {
    headers: authHeaders(),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao listar conversas`);
  return resp.json();
}

export async function obterConversa(
  tenantId: string,
  conversaId: string
): Promise<ConversaDetalhe> {
  const resp = await fetch(
    `${API_URL}/api/admin/escolas/${tenantId}/conversas/${conversaId}`,
    { headers: authHeaders() }
  );
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao abrir conversa`);
  return resp.json();
}

export async function listarBroadcasts(tenantId: string): Promise<BroadcastResumo[]> {
  const resp = await fetch(`${API_URL}/api/admin/escolas/${tenantId}/broadcasts`, {
    headers: authHeaders(),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao listar mensagens em massa`);
  return resp.json();
=======
// --------------------------- pais e salas --------------------------------- //
export interface Pai {
  id: string;
  nome: string;
  telefone: string;
}

export interface Sala {
  id: string;
  nome: string;
  descricao: string;
  total_pais: number;
  pais: Pai[];
}

async function jsonOuErro<T>(resp: Response, contexto: string): Promise<T> {
  if (!resp.ok) {
    const erro = await resp.json().catch(() => ({}));
    throw new Error(erro.detail ?? `Erro ${resp.status} ao ${contexto}`);
  }
  return resp.json() as Promise<T>;
}

// ----- pais (CRUD) ----- //
export async function listarPais(): Promise<Pai[]> {
  const resp = await fetch(`${API_URL}/api/admin/pais/tenant/${tenantEmFoco()}`, {
    headers: authHeaders(),
  });
  return jsonOuErro(resp, "listar pais");
}

export async function cadastrarPai(
  nome: string,
  telefone: string,
  salaIds: string[] = []
): Promise<Pai> {
  const resp = await fetch(`${API_URL}/api/admin/pais`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), nome, telefone, sala_ids: salaIds }),
  });
  return jsonOuErro(resp, "cadastrar responsável");
}

export async function atualizarPai(
  contatoId: string,
  nome: string,
  telefone: string
): Promise<Pai> {
  const resp = await fetch(`${API_URL}/api/admin/pais/${contatoId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), nome, telefone }),
  });
  return jsonOuErro(resp, "atualizar responsável");
}

export async function removerPai(contatoId: string): Promise<void> {
  const resp = await fetch(
    `${API_URL}/api/admin/pais/${contatoId}?tenant_id=${tenantEmFoco()}`,
    { method: "DELETE", headers: authHeaders() }
  );
  if (!resp.ok && resp.status !== 204) {
    const erro = await resp.json().catch(() => ({}));
    throw new Error(erro.detail ?? `Erro ${resp.status} ao remover responsável`);
  }
}

// ----- salas (CRUD) ----- //
export async function listarSalas(): Promise<Sala[]> {
  const resp = await fetch(`${API_URL}/api/admin/salas/tenant/${tenantEmFoco()}`, {
    headers: authHeaders(),
  });
  return jsonOuErro(resp, "listar salas");
}

export async function criarSala(nome: string, descricao = ""): Promise<Sala> {
  const resp = await fetch(`${API_URL}/api/admin/salas`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), nome, descricao }),
  });
  return jsonOuErro(resp, "criar sala");
}

export async function atualizarSala(
  salaId: string,
  nome: string,
  descricao: string
): Promise<Sala> {
  const resp = await fetch(`${API_URL}/api/admin/salas/${salaId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), nome, descricao }),
  });
  return jsonOuErro(resp, "atualizar sala");
}

export async function removerSala(salaId: string): Promise<void> {
  const resp = await fetch(
    `${API_URL}/api/admin/salas/${salaId}?tenant_id=${tenantEmFoco()}`,
    { method: "DELETE", headers: authHeaders() }
  );
  if (!resp.ok && resp.status !== 204) {
    const erro = await resp.json().catch(() => ({}));
    throw new Error(erro.detail ?? `Erro ${resp.status} ao remover sala`);
  }
}

// ----- vínculo e relatório ----- //
export async function vincularPaiASala(salaId: string, contatoId: string): Promise<void> {
  const resp = await fetch(`${API_URL}/api/admin/salas/${salaId}/pais`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), contato_id: contatoId }),
  });
  if (!resp.ok && resp.status !== 204) {
    const erro = await resp.json().catch(() => ({}));
    throw new Error(erro.detail ?? `Erro ${resp.status} ao vincular responsável`);
  }
}

export async function desvincularPaiDaSala(salaId: string, contatoId: string): Promise<void> {
  const resp = await fetch(
    `${API_URL}/api/admin/salas/${salaId}/pais/${contatoId}?tenant_id=${tenantEmFoco()}`,
    { method: "DELETE", headers: authHeaders() }
  );
  if (!resp.ok && resp.status !== 204) {
    const erro = await resp.json().catch(() => ({}));
    throw new Error(erro.detail ?? `Erro ${resp.status} ao desvincular responsável`);
  }
}

export async function relatorioPaisDaSala(salaId: string): Promise<Pai[]> {
  const resp = await fetch(
    `${API_URL}/api/admin/salas/${salaId}/pais?tenant_id=${tenantEmFoco()}`,
    { headers: authHeaders() }
  );
  return jsonOuErro(resp, "obter relatório de pais da sala");
}

// --------------------- base de conhecimento (RAG) ------------------------- //
export interface FonteConhecimento {
  id: string;
  nome: string;
  tipo: string;
  total_trechos: number;
  criado_em: string;
}

export async function listarConhecimento(): Promise<FonteConhecimento[]> {
  const resp = await fetch(`${API_URL}/api/admin/conhecimento/tenant/${tenantEmFoco()}`, {
    headers: authHeaders(),
  });
  return jsonOuErro(resp, "listar documentos");
}

export async function adicionarConhecimento(
  nome: string,
  conteudo: string,
  tipo: string
): Promise<FonteConhecimento> {
  const resp = await fetch(`${API_URL}/api/admin/conhecimento`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), nome, conteudo, tipo }),
  });
  return jsonOuErro(resp, "enviar documento");
}

export async function removerConhecimento(fonteId: string): Promise<void> {
  const resp = await fetch(
    `${API_URL}/api/admin/conhecimento/${fonteId}?tenant_id=${tenantEmFoco()}`,
    { method: "DELETE", headers: authHeaders() }
  );
  if (!resp.ok && resp.status !== 204) {
    const erro = await resp.json().catch(() => ({}));
    throw new Error(erro.detail ?? `Erro ${resp.status} ao remover documento`);
  }
}

// --------------------- system prompt do tenant ---------------------------- //
export interface PromptTenant {
  tenant_id: string;
  conteudo: string;
  atualizado_em: string | null;
}

export async function obterPrompt(): Promise<PromptTenant> {
  const resp = await fetch(`${API_URL}/api/admin/prompt/tenant/${tenantEmFoco()}`, {
    headers: authHeaders(),
  });
  return jsonOuErro(resp, "obter instruções da escola");
}

export async function salvarPrompt(conteudo: string): Promise<PromptTenant> {
  const resp = await fetch(`${API_URL}/api/admin/prompt`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), conteudo }),
  });
  return jsonOuErro(resp, "salvar instruções da escola");
>>>>>>> origin/main
}
