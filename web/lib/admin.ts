// Cliente da API administrativa + sessão baseada em token JWT (em localStorage).
//
// A autenticação do back-end é por JWT: o POST /login devolve um token; guardamos o
// token (não a senha) e o reenviamos em cada chamada via Authorization: Bearer.

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
  token: string;
  expiraEm: number; // epoch (ms) em que o token deixa de valer
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

export interface Licenca {
  status: "ativo" | "bloqueado" | "cancelado";
  motivo_bloqueio: string;
  bloqueado_em: string | null;
  plano: "mensal" | "anual";
  licenca_expira_em: string | null;
  dias_para_expirar: number | null;
  licenca_expirada: boolean;
  valor_mensal_centavos: number;
  valor_anual_centavos: number;
  cancelado_em: string | null;
  motivo_cancelamento: string;
}

export interface MetricasUso {
  total_usuarios_ativos: number;
  total_contatos: number;
  total_alunos: number;
  total_conversas: number;
  total_broadcasts: number;
}

export interface FichaFinanceira {
  tenant_id: string;
  nome: string;
  slug: string;
  criado_em: string;
  dias_de_casa: number;
  cancelado_em: string | null;
  motivo_cancelamento: string;
  status: "ativo" | "bloqueado" | "cancelado";
  plano: "mensal" | "anual";
  licenca_expira_em: string | null;
  dias_para_expirar: number | null;
  status_pagamento: "em_dia" | "a_vencer" | "vencido" | "inadimplente" | "cancelado";
  valor_mensal_centavos: number;
  valor_anual_centavos: number;
  mrr_centavos: number;
  arr_centavos: number;
  receita_acumulada_centavos: number;
  meses_ativos: number;
  uso: MetricasUso;
  limite_diario_meta: number;
  health_score: number;
}

export interface Escola {
  id: string;
  nome: string;
  slug: string;
  criado_em: string;
  total_conversas: number;
  total_contatos: number;
  total_broadcasts: number;
  licenca: Licenca;
}

export interface AvisoLicenca {
  tenant_id: string;
  nome: string;
  dias_para_expirar: number;
  destinatarios: string[];
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
  template_nome: string;
  criado_em: string;
  agendado_para: string | null;
  total_destinatarios: number;
  por_status: Record<string, number>;
}

export interface DestinatarioBroadcast {
  contato: string;
  nome: string;
  status: string;
  atualizado_em: string | null;
}

export interface BroadcastDetalhe {
  id: string;
  titulo: string;
  status: string;
  template_nome: string;
  criado_em: string;
  agendado_para: string | null;
  total_destinatarios: number;
  por_status: Record<string, number>;
  destinatarios: DestinatarioBroadcast[];
}

export interface RegistroAuditoria {
  id: string;
  tenant_id: string | null;
  ator: "usuario" | "llm" | "sistema";
  ator_id: string;
  ator_nome: string;
  acao: string;
  descricao: string;
  metadados: Record<string, unknown>;
  criado_em: string;
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
  if (!raw) return null;
  const s = JSON.parse(raw) as Sessao;
  // Token expirado: limpa a sessão para forçar novo login.
  if (s.expiraEm && Date.now() >= s.expiraEm) {
    window.localStorage.removeItem(STORAGE_KEY);
    return null;
  }
  return s;
}

function setSessao(s: Sessao) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
}

export function logout() {
  window.localStorage.removeItem(STORAGE_KEY);
}

// Erro lançado quando a sessão não vale mais (token expirado no cliente ou
// rejeitado pelo back-end com 401): a UI deve voltar ao login.
export class SessaoExpiradaError extends Error {
  constructor() {
    super("Sessão expirada");
    this.name = "SessaoExpiradaError";
  }
}

// Redireciona para o login e descarta a sessão atual. Usado tanto no 401 do
// back-end quanto quando o token já expirou do lado do cliente.
function redirecionarParaLogin() {
  logout();
  if (typeof window !== "undefined") {
    window.location.replace("/admin/login");
  }
}

function authHeaders(): Record<string, string> {
  const s = getSessao();
  if (!s) {
    // getSessao já removeu o token expirado; força o retorno ao login.
    redirecionarParaLogin();
    throw new SessaoExpiradaError();
  }
  return { Authorization: `Bearer ${s.token}` };
}

// Wrapper de fetch para as chamadas autenticadas. Se o token for recusado pelo
// back-end (401) — por expiração, troca do JWT_SECRET, usuário desativado, etc. —
// limpa a sessão e redireciona para o login, em vez de deixar o painel "logado"
// porém quebrado exibindo apenas toasts de erro.
async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const resp = await fetch(input, init);
  if (resp.status === 401) {
    redirecionarParaLogin();
    throw new SessaoExpiradaError();
  }
  return resp;
}

// O tenant em foco: super admin opera sobre o tenant demo; admin usa o seu.
export function tenantEmFoco(): string {
  const s = getSessao();
  return s?.usuario.tenant_id ?? DEMO_TENANT_ID;
}

// --------------------------- chamadas ------------------------------------- //
interface RespostaLogin {
  access_token: string;
  token_type: string;
  expira_em: number; // segundos
  usuario: Usuario;
}

export async function login(email: string, senha: string): Promise<Usuario> {
  const resp = await fetch(`${API_URL}/api/admin/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, senha }),
  });
  if (!resp.ok) {
    // 403 = escola bloqueada (traz o motivo no detail); 401 = credenciais inválidas.
    if (resp.status === 403) {
      const corpo = await resp.json().catch(() => ({}));
      throw new Error(corpo.detail ?? "Acesso bloqueado.");
    }
    throw new Error("Credenciais inválidas");
  }
  const dados = (await resp.json()) as RespostaLogin;
  setSessao({
    usuario: dados.usuario,
    token: dados.access_token,
    expiraEm: Date.now() + dados.expira_em * 1000,
  });
  return dados.usuario;
}

export async function listarGrupos(): Promise<Grupo[]> {
  const resp = await apiFetch(`${API_URL}/api/admin/grupos/${tenantEmFoco()}`, {
    headers: authHeaders(),
  });
  if (!resp.ok) throw new Error(`Erro ${resp.status} ao listar grupos`);
  return resp.json();
}

export async function criarGrupo(nome: string, descricao: string): Promise<Grupo> {
  const resp = await apiFetch(`${API_URL}/api/admin/grupos`, {
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
  const resp = await apiFetch(`${API_URL}/api/admin/grupos/${grupoId}/contatos`, {
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
  const resp = await apiFetch(`${API_URL}/api/admin/grupos/${grupoId}/enviar`, {
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
  const resp = await apiFetch(`${API_URL}/api/broadcasts/quota/${tenantId}`, {
    headers: authHeaders(),
  });
  if (!resp.ok) throw new Error(`Erro ${resp.status} ao consultar cota`);
  return resp.json();
}

// --------------------------- escolas (super admin) ------------------------- //
async function erroDe(resp: Response, padrao: string): Promise<Error> {
  const corpo = await resp.json().catch(() => ({}));
  return new Error(corpo.detail ?? padrao);
}

export async function listarEscolas(): Promise<Escola[]> {
  const resp = await apiFetch(`${API_URL}/api/admin/escolas`, { headers: authHeaders() });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao listar escolas`);
  return resp.json();
}

export async function obterEscola(id: string): Promise<Escola> {
  const resp = await apiFetch(`${API_URL}/api/admin/escolas/${id}`, { headers: authHeaders() });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao carregar escola`);
  return resp.json();
}

export async function criarEscola(nome: string, slug: string): Promise<Escola> {
  const resp = await apiFetch(`${API_URL}/api/admin/escolas`, {
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
  const resp = await apiFetch(`${API_URL}/api/admin/escolas/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ nome, slug }),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao atualizar escola`);
  return resp.json();
}

export async function removerEscola(id: string): Promise<void> {
  const resp = await apiFetch(`${API_URL}/api/admin/escolas/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!resp.ok && resp.status !== 204) {
    throw await erroDe(resp, `Erro ${resp.status} ao remover escola`);
  }
}

// --------------------- licenciamento / bloqueio (super admin) -------------- //
export async function bloquearEscola(id: string, motivo: string): Promise<Escola> {
  const resp = await apiFetch(`${API_URL}/api/admin/escolas/${id}/bloquear`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ motivo }),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao bloquear escola`);
  return resp.json();
}

export async function desbloquearEscola(id: string): Promise<Escola> {
  const resp = await apiFetch(`${API_URL}/api/admin/escolas/${id}/desbloquear`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao desbloquear escola`);
  return resp.json();
}

export async function cancelarEscola(id: string, motivo: string): Promise<Escola> {
  const resp = await apiFetch(`${API_URL}/api/admin/escolas/${id}/cancelar`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ motivo }),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao cancelar escola`);
  return resp.json();
}

export async function reativarEscola(id: string): Promise<Escola> {
  const resp = await apiFetch(`${API_URL}/api/admin/escolas/${id}/reativar`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao reativar escola`);
  return resp.json();
}

export async function definirLicenca(
  id: string,
  plano: "mensal" | "anual",
  licencaExpiraEm: string | null,
  valorMensalCentavos?: number | null,
  valorAnualCentavos?: number | null
): Promise<Escola> {
  const resp = await apiFetch(`${API_URL}/api/admin/escolas/${id}/licenca`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      plano,
      licenca_expira_em: licencaExpiraEm,
      valor_mensal_centavos: valorMensalCentavos ?? null,
      valor_anual_centavos: valorAnualCentavos ?? null,
    }),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao definir licença`);
  return resp.json();
}

export async function obterFichaFinanceira(id: string): Promise<FichaFinanceira> {
  const resp = await apiFetch(`${API_URL}/api/admin/escolas/${id}/ficha-financeira`, {
    headers: authHeaders(),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao carregar ficha financeira`);
  return resp.json();
}

export async function notificarVencimento(): Promise<AvisoLicenca[]> {
  const resp = await apiFetch(`${API_URL}/api/admin/licencas/notificar-vencimento`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao notificar vencimentos`);
  return resp.json();
}

// --------------------------- conversas e broadcasts ------------------------ //
export async function listarConversas(tenantId: string): Promise<ConversaResumo[]> {
  const resp = await apiFetch(`${API_URL}/api/admin/escolas/${tenantId}/conversas`, {
    headers: authHeaders(),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao listar conversas`);
  return resp.json();
}

export async function obterConversa(
  tenantId: string,
  conversaId: string
): Promise<ConversaDetalhe> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/escolas/${tenantId}/conversas/${conversaId}`,
    { headers: authHeaders() }
  );
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao abrir conversa`);
  return resp.json();
}

export async function listarBroadcasts(tenantId: string): Promise<BroadcastResumo[]> {
  const resp = await apiFetch(`${API_URL}/api/admin/escolas/${tenantId}/broadcasts`, {
    headers: authHeaders(),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao listar mensagens em massa`);
  return resp.json();
}

export async function obterBroadcast(
  tenantId: string,
  broadcastId: string
): Promise<BroadcastDetalhe> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/escolas/${tenantId}/broadcasts/${broadcastId}`,
    { headers: authHeaders() }
  );
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao abrir o disparo`);
  return resp.json();
}

// --------------------------- auditoria ------------------------------------ //
export async function listarAuditoria(tenantId: string): Promise<RegistroAuditoria[]> {
  const resp = await apiFetch(`${API_URL}/api/admin/escolas/${tenantId}/auditoria`, {
    headers: authHeaders(),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao listar a auditoria`);
  return resp.json();
}

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
  professor_id: string | null;
  professor_nome: string;
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
  const resp = await apiFetch(`${API_URL}/api/admin/pais/tenant/${tenantEmFoco()}`, {
    headers: authHeaders(),
  });
  return jsonOuErro(resp, "listar pais");
}

export async function cadastrarPai(
  nome: string,
  telefone: string,
  salaIds: string[] = []
): Promise<Pai> {
  const resp = await apiFetch(`${API_URL}/api/admin/pais`, {
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
  const resp = await apiFetch(`${API_URL}/api/admin/pais/${contatoId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), nome, telefone }),
  });
  return jsonOuErro(resp, "atualizar responsável");
}

export async function removerPai(contatoId: string): Promise<void> {
  const resp = await apiFetch(
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
  const resp = await apiFetch(`${API_URL}/api/admin/salas/tenant/${tenantEmFoco()}`, {
    headers: authHeaders(),
  });
  return jsonOuErro(resp, "listar salas");
}

export async function criarSala(nome: string, descricao = ""): Promise<Sala> {
  const resp = await apiFetch(`${API_URL}/api/admin/salas`, {
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
  const resp = await apiFetch(`${API_URL}/api/admin/salas/${salaId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), nome, descricao }),
  });
  return jsonOuErro(resp, "atualizar sala");
}

// Remove uma série. Sem `moverPara`, exclui os alunos da série junto; com `moverPara`,
// transfere os alunos para a série indicada antes de remover esta.
export async function removerSala(salaId: string, moverPara?: string): Promise<void> {
  const params = new URLSearchParams({ tenant_id: tenantEmFoco() });
  if (moverPara) params.set("mover_para", moverPara);
  const resp = await apiFetch(`${API_URL}/api/admin/salas/${salaId}?${params.toString()}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!resp.ok && resp.status !== 204) {
    const erro = await resp.json().catch(() => ({}));
    throw new Error(erro.detail ?? `Erro ${resp.status} ao remover sala`);
  }
}

// ----- vínculo e relatório ----- //
export async function vincularPaiASala(salaId: string, contatoId: string): Promise<void> {
  const resp = await apiFetch(`${API_URL}/api/admin/salas/${salaId}/pais`, {
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
  const resp = await apiFetch(
    `${API_URL}/api/admin/salas/${salaId}/pais/${contatoId}?tenant_id=${tenantEmFoco()}`,
    { method: "DELETE", headers: authHeaders() }
  );
  if (!resp.ok && resp.status !== 204) {
    const erro = await resp.json().catch(() => ({}));
    throw new Error(erro.detail ?? `Erro ${resp.status} ao desvincular responsável`);
  }
}

export async function relatorioPaisDaSala(salaId: string): Promise<Pai[]> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/salas/${salaId}/pais?tenant_id=${tenantEmFoco()}`,
    { headers: authHeaders() }
  );
  return jsonOuErro(resp, "obter relatório de pais da sala");
}

// ----- cobertura de contatos (alunos sem responsável com telefone) ----- //
export interface AlunoResumo {
  id: string;
  nome: string;
  matricula: string;
}

export interface CoberturaSala {
  sala_id: string;
  sala_nome: string;
  total_alunos: number;
  total_sem_contato: number;
  alunos_sem_contato: AlunoResumo[];
}

export interface ResultadoNotificacaoProfessor {
  enviado: boolean;
  id_externo: string;
  telefone: string;
  total_sem_contato: number;
  cobertura: CoberturaSala;
}

export async function coberturaDasSalas(): Promise<CoberturaSala[]> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/salas/tenant/${tenantEmFoco()}/cobertura`,
    { headers: authHeaders() }
  );
  return jsonOuErro(resp, "carregar cobertura de contatos das salas");
}

export async function coberturaDaSala(salaId: string): Promise<CoberturaSala> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/salas/${salaId}/cobertura?tenant_id=${tenantEmFoco()}`,
    { headers: authHeaders() }
  );
  return jsonOuErro(resp, "carregar cobertura de contatos da sala");
}

// Dispara ao professor um aviso pedindo os contatos de responsáveis faltantes.
export async function notificarProfessor(
  salaId: string,
  telefone: string,
  mensagem = ""
): Promise<ResultadoNotificacaoProfessor> {
  const resp = await apiFetch(`${API_URL}/api/admin/salas/${salaId}/notificar-professor`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), telefone, mensagem }),
  });
  return jsonOuErro(resp, "notificar professor");
}

// --------------------------------- alunos --------------------------------- //
export interface Aluno {
  id: string;
  nome: string;
  matricula: string;
  ativo: boolean;
  sala_id: string;
  sala_nome: string;
  responsaveis: Pai[];
}

export async function listarAlunos(salaId?: string): Promise<Aluno[]> {
  const qs = salaId ? `?sala_id=${salaId}` : "";
  const resp = await apiFetch(
    `${API_URL}/api/admin/alunos/tenant/${tenantEmFoco()}${qs}`,
    { headers: authHeaders() }
  );
  return jsonOuErro(resp, "listar alunos");
}

export async function cadastrarAluno(
  nome: string,
  salaId: string,
  matricula = "",
  responsavelIds: string[] = []
): Promise<Aluno> {
  const resp = await apiFetch(`${API_URL}/api/admin/alunos`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      tenant_id: tenantEmFoco(),
      nome,
      matricula,
      sala_id: salaId,
      responsavel_ids: responsavelIds,
    }),
  });
  return jsonOuErro(resp, "cadastrar aluno");
}

export async function atualizarAluno(
  alunoId: string,
  nome: string,
  salaId: string,
  matricula: string,
  ativo: boolean
): Promise<Aluno> {
  const resp = await apiFetch(`${API_URL}/api/admin/alunos/${alunoId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      tenant_id: tenantEmFoco(),
      nome,
      matricula,
      sala_id: salaId,
      ativo,
    }),
  });
  return jsonOuErro(resp, "atualizar aluno");
}

export async function removerAluno(alunoId: string): Promise<void> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/alunos/${alunoId}?tenant_id=${tenantEmFoco()}`,
    { method: "DELETE", headers: authHeaders() }
  );
  if (!resp.ok && resp.status !== 204) {
    const erro = await resp.json().catch(() => ({}));
    throw new Error(erro.detail ?? `Erro ${resp.status} ao remover aluno`);
  }
}

export async function vincularResponsavelAoAluno(
  alunoId: string,
  contatoId: string
): Promise<void> {
  const resp = await apiFetch(`${API_URL}/api/admin/alunos/${alunoId}/responsaveis`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), contato_id: contatoId }),
  });
  if (!resp.ok && resp.status !== 204) {
    const erro = await resp.json().catch(() => ({}));
    throw new Error(erro.detail ?? `Erro ${resp.status} ao vincular responsável`);
  }
}

export async function desvincularResponsavelDoAluno(
  alunoId: string,
  contatoId: string
): Promise<void> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/alunos/${alunoId}/responsaveis/${contatoId}?tenant_id=${tenantEmFoco()}`,
    { method: "DELETE", headers: authHeaders() }
  );
  if (!resp.ok && resp.status !== 204) {
    const erro = await resp.json().catch(() => ({}));
    throw new Error(erro.detail ?? `Erro ${resp.status} ao desvincular responsável`);
  }
}

// ------------------------------ professores ------------------------------- //
export interface Professor {
  id: string;
  nome: string;
  telefone: string;
}

export async function listarProfessores(): Promise<Professor[]> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/professores/tenant/${tenantEmFoco()}`,
    { headers: authHeaders() }
  );
  return jsonOuErro(resp, "listar professores");
}

export async function cadastrarProfessor(
  nome: string,
  telefone: string
): Promise<Professor> {
  const resp = await apiFetch(`${API_URL}/api/admin/professores`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), nome, telefone }),
  });
  return jsonOuErro(resp, "cadastrar professor");
}

export async function atualizarProfessor(
  professorId: string,
  nome: string,
  telefone: string
): Promise<Professor> {
  const resp = await apiFetch(`${API_URL}/api/admin/professores/${professorId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), nome, telefone }),
  });
  return jsonOuErro(resp, "atualizar professor");
}

export async function removerProfessor(professorId: string): Promise<void> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/professores/${professorId}?tenant_id=${tenantEmFoco()}`,
    { method: "DELETE", headers: authHeaders() }
  );
  if (!resp.ok && resp.status !== 204) {
    const erro = await resp.json().catch(() => ({}));
    throw new Error(erro.detail ?? `Erro ${resp.status} ao remover professor`);
  }
}

export async function seriesDoProfessor(professorId: string): Promise<Sala[]> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/professores/${professorId}/series?tenant_id=${tenantEmFoco()}`,
    { headers: authHeaders() }
  );
  return jsonOuErro(resp, "listar séries do professor");
}

// Define (professorId) ou remove (professorId = null) o professor responsável pela série.
export async function definirProfessorDaSala(
  salaId: string,
  professorId: string | null
): Promise<Sala> {
  const resp = await apiFetch(`${API_URL}/api/admin/salas/${salaId}/professor`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), professor_id: professorId }),
  });
  return jsonOuErro(resp, "definir professor da série");
}

// --------------------- importação de alunos em massa ---------------------- //
export interface ResponsavelImportado {
  nome: string;
  telefone: string;
  aviso?: string;
}

export interface LinhaImportacaoAluno {
  nome: string;
  serie: string;
  matricula: string;
  responsaveis: ResponsavelImportado[];
  erros: string[];
  avisos: string[];
  serie_nova: boolean;
  valido: boolean;
}

export interface ImportacaoPrevia {
  linhas: LinhaImportacaoAluno[];
  series_existentes: string[];
  series_novas: string[];
  total_validos: number;
}

export interface ImportacaoResultado {
  criados: number;
  ignorados: number;
  series_criadas: string[];
  erros: string[];
}

export async function previaImportacaoAlunos(conteudo: string): Promise<ImportacaoPrevia> {
  const resp = await apiFetch(`${API_URL}/api/admin/alunos/importar/previa`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), conteudo }),
  });
  return jsonOuErro(resp, "pré-visualizar importação");
}

export async function confirmarImportacaoAlunos(
  linhas: LinhaImportacaoAluno[],
  criarSeriesAusentes: boolean
): Promise<ImportacaoResultado> {
  const resp = await apiFetch(`${API_URL}/api/admin/alunos/importar/confirmar`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      tenant_id: tenantEmFoco(),
      linhas,
      criar_series_ausentes: criarSeriesAusentes,
    }),
  });
  return jsonOuErro(resp, "confirmar importação");
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
  const resp = await apiFetch(`${API_URL}/api/admin/conhecimento/tenant/${tenantEmFoco()}`, {
    headers: authHeaders(),
  });
  return jsonOuErro(resp, "listar documentos");
}

export async function adicionarConhecimento(
  nome: string,
  conteudo: string,
  tipo: string
): Promise<FonteConhecimento> {
  const resp = await apiFetch(`${API_URL}/api/admin/conhecimento`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), nome, conteudo, tipo }),
  });
  return jsonOuErro(resp, "enviar documento");
}

export async function removerConhecimento(fonteId: string): Promise<void> {
  const resp = await apiFetch(
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
  const resp = await apiFetch(`${API_URL}/api/admin/prompt/tenant/${tenantEmFoco()}`, {
    headers: authHeaders(),
  });
  return jsonOuErro(resp, "obter instruções da escola");
}

export async function salvarPrompt(conteudo: string): Promise<PromptTenant> {
  const resp = await apiFetch(`${API_URL}/api/admin/prompt`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), conteudo }),
  });
  return jsonOuErro(resp, "salvar instruções da escola");
}
