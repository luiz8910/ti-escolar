// Cliente da API administrativa + sessão baseada em token JWT (em localStorage).
//
// A autenticação do back-end é por JWT: o POST /login devolve um token; guardamos o
// token (não a senha) e o reenviamos em cada chamada via Authorization: Bearer.

import { API_URL } from "./api";

// Template aprovado criado pelo seed (usado nos disparos do painel).
export const DEMO_TEMPLATE_ID = "00000000-0000-0000-0000-0000000000a1";

const STORAGE_KEY = "tiescolar.admin";

/** Posto na escola. A ordem da lista é a da hierarquia — maior manda em menor. */
export type Cargo = "diretor" | "vice_diretor" | "coordenador" | "secretaria";

export const CARGOS: { valor: Cargo; rotulo: string; nivel: number }[] = [
  { valor: "diretor", rotulo: "Diretor(a)", nivel: 4 },
  { valor: "vice_diretor", rotulo: "Vice-diretor(a)", nivel: 3 },
  { valor: "coordenador", rotulo: "Coordenador(a)", nivel: 2 },
  { valor: "secretaria", rotulo: "Secretaria", nivel: 1 },
];

export type Turno = "manha" | "tarde" | "integral" | "noite";

export const TURNOS: { valor: Turno; rotulo: string }[] = [
  { valor: "manha", rotulo: "Manhã" },
  { valor: "tarde", rotulo: "Tarde" },
  { valor: "integral", rotulo: "Integral" },
  { valor: "noite", rotulo: "Noite" },
];

export function nivelDoCargo(cargo: string): number {
  return CARGOS.find((c) => c.valor === cargo)?.nivel ?? 0;
}

export interface Usuario {
  id: string;
  nome: string;
  email: string;
  papel: "super_admin" | "tenant_admin" | "secretaria";
  tenant_id: string | null;
  /** Vazio para o super admin, que não ocupa cargo em escola nenhuma. */
  cargo: Cargo | "";
  cargo_rotulo: string;
  /** Pode abrir a tela de equipe e mexer em contas? A secretaria não pode. */
  gere_usuarios: boolean;
  telefone: string;
  endereco: string;
  turno: Turno | "";
  /** Nome da escola — só o login preenche; as listagens de usuário deixam vazio. */
  tenant_nome?: string;
  /** Funcionária desligada continua no cadastro (histórico), mas sem acesso ao painel. */
  ativo?: boolean;
  criado_em?: string | null;
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

/** Expediente da secretaria: decide se o assistente promete atendimento agora ou no
 *  próximo dia útil (§6j). É campo da escola, não texto da base de conhecimento. */
export interface Expediente {
  /** Dias no padrão ISO: 1 = segunda … 7 = domingo. */
  dias: number[];
  inicio: string; // "HH:MM"
  fim: string; // "HH:MM"
  timezone: string;
  descricao: string;
  aberto_agora: boolean;
}

export interface Escola {
  id: string;
  nome: string;
  slug: string;
  whatsapp_numero: string;
  /** phone_number_id do número da escola na Meta: origem do outbound e roteamento do inbound. */
  meta_phone_number_id: string;
  telefone_contato: string;
  expediente: Expediente | null;
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

/** Uma **sessão** de conversa (§13), não o fio eterno do responsável. */
export interface ConversaResumo {
  id: string;
  contato: string;
  criado_em: string;
  total_mensagens: number;
  ultima_mensagem: string;
  ultima_em: string | null;
  /** Sessão fechada por inatividade ou atendimento resolvido. `null` = em andamento. */
  encerrada_em: string | null;
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
  encerrada_em: string | null;
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
  /**
   * Id do usuário quando ele **ainda tem conta** — é o que autoriza o link para o
   * perfil. Vazio para LLM/sistema e para conta que não existe mais: um link para o
   * nada é pior que texto puro.
   */
  ator_perfil_id: string;
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
  // A escola em foco morre com a sessão: senão o próximo super admin a entrar neste
  // navegador herdaria a escola escolhida por outra pessoa, sem perceber.
  limparEscolaEmFoco();
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

// --------------------------- escola em foco -------------------------------- //
// O admin de escola é amarrado ao seu tenant e não escolhe nada. O super admin tem
// `tenant_id = NULL` e, desde que o seletor de escola saiu do painel, não tinha como
// dizer sobre qual escola estava operando: `tenantEmFoco()` devolvia o tenant de
// DEMONSTRAÇÃO, e toda tela de escola (instruções, base de conhecimento, alunos, turmas,
// atendimentos, documentos) agia silenciosamente sobre a escola errada.
//
// Agora a escola em foco é uma escolha explícita, guardada ao lado da sessão. Sem
// escolha, `tenantEmFoco()` **lança** em vez de chutar — errar de escola em silêncio é
// pior que uma tela pedindo para escolher.
const FOCO_KEY = "tiescolar.escolaEmFoco";

export interface EscolaEmFoco {
  tenantId: string;
  nome: string;
}

export class EscolaNaoSelecionadaError extends Error {
  constructor() {
    super("Selecione a escola em que deseja operar.");
    this.name = "EscolaNaoSelecionadaError";
  }
}

export function getEscolaEmFoco(): EscolaEmFoco | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(FOCO_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as EscolaEmFoco;
  } catch {
    return null;
  }
}

export function setEscolaEmFoco(escola: EscolaEmFoco) {
  window.localStorage.setItem(FOCO_KEY, JSON.stringify(escola));
}

export function limparEscolaEmFoco() {
  if (typeof window !== "undefined") window.localStorage.removeItem(FOCO_KEY);
}

/**
 * A escola sobre a qual as chamadas de tenant operam.
 *
 * - admin de escola: o próprio `tenant_id`, sempre — o foco guardado é ignorado;
 * - super admin: a escola escolhida. Sem escolha, lança `EscolaNaoSelecionadaError`.
 */
export function tenantEmFoco(): string {
  const s = getSessao();
  if (s?.usuario.tenant_id) return s.usuario.tenant_id;
  const foco = getEscolaEmFoco();
  if (foco?.tenantId) return foco.tenantId;
  throw new EscolaNaoSelecionadaError();
}

/** Precisa escolher uma escola antes de usar as telas de escola? */
export function exigeEscolhaDeEscola(): boolean {
  const s = getSessao();
  return Boolean(s) && !s?.usuario.tenant_id && !getEscolaEmFoco();
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

/** Campos do expediente enviados no cadastro/edição. Omitidos = mantém o atual. */
export interface ExpedienteEntrada {
  expediente_dias?: number[];
  expediente_inicio?: string;
  expediente_fim?: string;
  expediente_timezone?: string;
}

export async function criarEscola(
  nome: string,
  slug: string,
  whatsappNumero = "",
  telefoneContato = "",
  metaPhoneNumberId = "",
  expediente: ExpedienteEntrada = {}
): Promise<Escola> {
  const resp = await apiFetch(`${API_URL}/api/admin/escolas`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      nome,
      slug,
      whatsapp_numero: whatsappNumero,
      telefone_contato: telefoneContato,
      meta_phone_number_id: metaPhoneNumberId,
      ...expediente,
    }),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao criar escola`);
  return resp.json();
}

export async function atualizarEscola(
  id: string,
  nome: string,
  slug: string,
  whatsappNumero = "",
  telefoneContato = "",
  metaPhoneNumberId = "",
  expediente: ExpedienteEntrada = {}
): Promise<Escola> {
  const resp = await apiFetch(`${API_URL}/api/admin/escolas/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      nome,
      slug,
      whatsapp_numero: whatsappNumero,
      telefone_contato: telefoneContato,
      meta_phone_number_id: metaPhoneNumberId,
      ...expediente,
    }),
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
export async function listarConversas(
  tenantId: string,
  pagina?: number,
  porPagina?: number,
): Promise<Pagina<ConversaResumo>> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/escolas/${tenantId}/conversas${qsPaginacao(pagina, porPagina)}`,
    { headers: authHeaders() },
  );
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

export async function listarBroadcasts(
  tenantId: string,
  pagina?: number,
  porPagina?: number,
): Promise<Pagina<BroadcastResumo>> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/escolas/${tenantId}/broadcasts${qsPaginacao(pagina, porPagina)}`,
    { headers: authHeaders() },
  );
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
export async function listarAuditoria(
  tenantId: string,
  pagina?: number,
  porPagina?: number,
): Promise<Pagina<RegistroAuditoria>> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/escolas/${tenantId}/auditoria${qsPaginacao(pagina, porPagina)}`,
    { headers: authHeaders() },
  );
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao listar a auditoria`);
  return resp.json();
}

// --------------------------- pais e salas --------------------------------- //
/** Vínculo do responsável com o aluno. `responsavel_legal` é o termo de guarda. */
export type TipoFiliacao = "mae" | "pai" | "responsavel_legal" | "outro";

export const TIPOS_FILIACAO: { valor: TipoFiliacao; rotulo: string }[] = [
  { valor: "mae", rotulo: "Mãe" },
  { valor: "pai", rotulo: "Pai" },
  { valor: "responsavel_legal", rotulo: "Responsável legal (termo de guarda)" },
  { valor: "outro", rotulo: "Outro" },
];

export interface Pai {
  id: string;
  nome: string;
  /** O número da conversa: roteia o inbound e recebe os disparos. */
  telefone: string;
  cpf: string;
  /** CPF já pontuado pelo back-end — a tela não formata nada. */
  cpf_formatado: string;
  tipo_filiacao: TipoFiliacao | "";
  tipo_filiacao_rotulo: string;
  data_nascimento: string;
  /** Emergência. **Não** recebe disparo — a tela diz isso em texto. */
  telefone_2: string;
  local_trabalho: string;
  telefone_trabalho: string;
  email: string;
  ativo: boolean;
}

/** Cadastro civil e de contato do responsável, na forma que a API recebe. */
export interface DadosResponsavel {
  cpf: string;
  tipo_filiacao: TipoFiliacao | "";
  data_nascimento: string;
  telefone_2: string;
  local_trabalho: string;
  telefone_trabalho: string;
  email: string;
}

export const DADOS_RESPONSAVEL_VAZIO: DadosResponsavel = {
  cpf: "",
  tipo_filiacao: "",
  data_nascimento: "",
  telefone_2: "",
  local_trabalho: "",
  telefone_trabalho: "",
  email: "",
};

/** Extrai os campos de cadastro de um responsável já carregado (para editar). */
export function dadosDoResponsavel(p: Pai): DadosResponsavel {
  return {
    cpf: p.cpf,
    tipo_filiacao: p.tipo_filiacao,
    data_nascimento: p.data_nascimento,
    telefone_2: p.telefone_2,
    local_trabalho: p.local_trabalho,
    telefone_trabalho: p.telefone_trabalho,
    email: p.email,
  };
}

/** Formatos da grade (decisão B: os dois, sobre a mesma coluna JSON). */
export type FormatoGrade = "turno" | "aulas";

export interface BlocoGrade {
  /** Dia ISO: 1 = segunda … 7 = domingo. */
  dia: number;
  inicio: string;
  fim: string;
  tipo: "aula" | "intervalo";
  rotulo: string;
}

export interface Grade {
  formato?: FormatoGrade;
  // formato "turno"
  inicio?: string;
  fim?: string;
  intervalo_inicio?: string;
  intervalo_minutos?: number;
  // formato "aulas"
  blocos?: BlocoGrade[];
}

/**
 * Disciplinas do ensino fundamental, para escolher no lugar de digitar.
 *
 * São os componentes curriculares da BNCC (áreas de Linguagens, Matemática, Ciências da
 * Natureza e Ciências Humanas) mais os que quase toda escola tem na prática — Ensino
 * Religioso, Projeto de Vida, Informática.
 *
 * **É sugestão, não trava.** O campo continua aceitando texto livre: escola tem
 * "Robótica", "Xadrez", "Reforço", e uma lista fechada exigiria um deploy nosso para cada
 * uma. Por isso é um combo (`datalist`) e não um `select` — quem reconhece a disciplina
 * escolhe em um clique, quem não a encontra escreve.
 */
export const DISCIPLINAS_FUNDAMENTAL = [
  "Língua Portuguesa",
  "Matemática",
  "Ciências",
  "História",
  "Geografia",
  "Arte",
  "Educação Física",
  "Língua Inglesa",
  "Ensino Religioso",
  "Informática",
  "Projeto de Vida",
  "Leitura",
  "Reforço",
];

export const DIAS_SEMANA = [
  { valor: 1, curto: "Seg" },
  { valor: 2, curto: "Ter" },
  { valor: 3, curto: "Qua" },
  { valor: 4, curto: "Qui" },
  { valor: 5, curto: "Sex" },
  { valor: 6, curto: "Sáb" },
];

export interface Sala {
  id: string;
  /** Derivado de etapa + turma pelo back-end. */
  nome: string;
  descricao: string;
  ano_letivo: number;
  etapa: string;
  turma: string;
  numero_sala: string;
  periodo: Turno | "";
  grade_horario: Grade;
  /** Minutos de aula por semana — só o formato "aulas" tem o dado. */
  minutos_de_aula: number;
  /** Responsáveis **derivados dos alunos ativos**, não vinculados à mão. */
  total_pais: number;
  pais: Pai[];
  professor_id: string | null;
  professor_nome: string;
}

/** Identificação e grade da turma, na forma que a API recebe. */
export interface DadosTurma {
  ano_letivo: number;
  etapa: string;
  turma: string;
  numero_sala: string;
  periodo: Turno | "";
  grade_horario: Grade;
}

export function dadosDaTurma(s: Sala): DadosTurma {
  return {
    ano_letivo: s.ano_letivo,
    etapa: s.etapa,
    turma: s.turma,
    numero_sala: s.numero_sala,
    periodo: s.periodo,
    grade_horario: s.grade_horario ?? {},
  };
}

export function turmaVazia(): DadosTurma {
  return {
    ano_letivo: new Date().getFullYear(),
    etapa: "",
    turma: "",
    numero_sala: "",
    periodo: "",
    grade_horario: { formato: "turno" },
  };
}

async function jsonOuErro<T>(resp: Response, contexto: string): Promise<T> {
  if (!resp.ok) {
    const erro = await resp.json().catch(() => ({}));
    throw new Error(erro.detail ?? `Erro ${resp.status} ao ${contexto}`);
  }
  return resp.json() as Promise<T>;
}

// ----- pais (CRUD) ----- //
export async function listarPais(
  pagina?: number,
  porPagina?: number,
): Promise<Pagina<Pai>> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/pais/tenant/${tenantEmFoco()}${qsPaginacao(pagina, porPagina)}`,
    { headers: authHeaders() },
  );
  return jsonOuErro(resp, "listar pais");
}

/**
 * Todos os responsáveis da escola, percorrendo as páginas até o fim.
 *
 * As telas que **vinculam** um responsável (a uma turma, a um aluno) precisam do
 * conjunto, não de uma página: pedir só a primeira faria sumir do seletor quem está
 * além dela — e o vínculo com essa pessoa ficaria impossível pela tela.
 */
export async function listarTodosOsPais(porPagina = 200): Promise<Pai[]> {
  const primeira = await listarPais(1, porPagina);
  const todos = [...primeira.itens];
  for (let pagina = 2; pagina <= primeira.meta.total_paginas; pagina++) {
    const seguinte = await listarPais(pagina, porPagina);
    todos.push(...seguinte.itens);
  }
  return todos;
}

export async function cadastrarPai(
  nome: string,
  telefone: string,
  salaIds: string[] = [],
  dados: DadosResponsavel = DADOS_RESPONSAVEL_VAZIO
): Promise<Pai> {
  const resp = await apiFetch(`${API_URL}/api/admin/pais`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      tenant_id: tenantEmFoco(),
      nome,
      telefone,
      sala_ids: salaIds,
      ...dados,
    }),
  });
  return jsonOuErro(resp, "cadastrar responsável");
}

export async function atualizarPai(
  contatoId: string,
  nome: string,
  telefone: string,
  dados: DadosResponsavel = DADOS_RESPONSAVEL_VAZIO
): Promise<Pai> {
  const resp = await apiFetch(`${API_URL}/api/admin/pais/${contatoId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), nome, telefone, ...dados }),
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

/**
 * `nome` é opcional quando `dados` traz etapa + turma: o back-end o deriva dos dois.
 * Continua aceito sozinho para a criação rápida (ex.: a série destino ao excluir uma turma).
 */
export async function criarSala(
  nome = "",
  descricao = "",
  dados?: DadosTurma
): Promise<Sala> {
  const resp = await apiFetch(`${API_URL}/api/admin/salas`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), nome, descricao, ...(dados ?? {}) }),
  });
  return jsonOuErro(resp, "criar turma");
}

export async function atualizarSala(
  salaId: string,
  nome: string,
  descricao: string,
  dados?: DadosTurma
): Promise<Sala> {
  const resp = await apiFetch(`${API_URL}/api/admin/salas/${salaId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), nome, descricao, ...(dados ?? {}) }),
  });
  return jsonOuErro(resp, "atualizar turma");
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
// `vincularPaiASala`/`desvincularPaiDaSala` não existem mais: a lista de responsáveis da
// turma é **derivada dos alunos ativos**. Quem muda essa lista é o vínculo
// aluno↔responsável, na tela de Alunos.

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
  /** false = ex-aluno. O registro nunca é apagado (soft delete). */
  ativo: boolean;
  desativado_em: string | null;
  motivo_desativacao: string;
  sala_id: string;
  sala_nome: string;
  responsaveis: Pai[];
  /** A foto é opcional. Os bytes saem por `urlFotoAluno`, nunca por URL pública. */
  tem_foto: boolean;
}

// --------------------------- foto do aluno -------------------------------- //
/**
 * Envia a foto em base64 — o navegador lê o arquivo e manda o conteúdo, mesmo caminho do
 * upload da base de conhecimento. Sem multipart no servidor.
 */
export async function definirFotoAluno(alunoId: string, arquivo: File): Promise<Aluno> {
  const base64 = await new Promise<string>((resolve, reject) => {
    const leitor = new FileReader();
    leitor.onerror = () => reject(new Error("Não foi possível ler o arquivo."));
    // `readAsDataURL` devolve "data:image/jpeg;base64,XXXX" — só o depois da vírgula.
    leitor.onload = () => resolve(String(leitor.result).split(",")[1] ?? "");
    leitor.readAsDataURL(arquivo);
  });
  const resp = await apiFetch(`${API_URL}/api/admin/alunos/${alunoId}/foto`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      tenant_id: tenantEmFoco(),
      conteudo_base64: base64,
      mime: arquivo.type,
    }),
  });
  return jsonOuErro(resp, "enviar a foto");
}

export async function removerFotoAluno(alunoId: string): Promise<Aluno> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/alunos/${alunoId}/foto?tenant_id=${tenantEmFoco()}`,
    { method: "DELETE", headers: authHeaders() }
  );
  return jsonOuErro(resp, "remover a foto");
}

/**
 * Baixa a foto e devolve um blob URL para exibir.
 *
 * O endpoint é autenticado, então não dá para pendurar a URL num `<img src>` — o
 * navegador não manda o cabeçalho `Authorization`. Quem chamar precisa revogar o blob ao
 * desmontar, senão a imagem fica na memória da aba.
 */
export async function urlFotoAluno(alunoId: string): Promise<string | null> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/alunos/${alunoId}/foto?tenant_id=${tenantEmFoco()}`,
    { headers: authHeaders() }
  );
  if (!resp.ok) return null;
  return URL.createObjectURL(await resp.blob());
}

/** `apenasAtivos`: undefined = todos; true = matriculados; false = ex-alunos. */
export async function listarAlunos(
  salaId?: string,
  apenasAtivos?: boolean,
  pagina?: number,
  porPagina?: number,
): Promise<Pagina<Aluno>> {
  const params = new URLSearchParams();
  if (salaId) params.set("sala_id", salaId);
  if (apenasAtivos !== undefined) params.set("apenas_ativos", String(apenasAtivos));
  if (pagina) params.set("pagina", String(pagina));
  if (porPagina) params.set("por_pagina", String(porPagina));
  const qs = params.toString() ? `?${params.toString()}` : "";
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

/**
 * Desativa o aluno — **soft delete**. Nada é apagado: o registro de que ele estudou na
 * escola é o lastro que o histórico escolar e as declarações exigem.
 */
export async function desativarAluno(alunoId: string, motivo = ""): Promise<Aluno> {
  const params = new URLSearchParams({ tenant_id: tenantEmFoco() });
  if (motivo) params.set("motivo", motivo);
  const resp = await apiFetch(
    `${API_URL}/api/admin/alunos/${alunoId}?${params.toString()}`,
    { method: "DELETE", headers: authHeaders() }
  );
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao desativar aluno`);
  return resp.json();
}

/** Rematrícula do ex-aluno — ou desfaz uma desativação feita por engano. */
export async function reativarAluno(alunoId: string): Promise<Aluno> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/alunos/${alunoId}/reativar?tenant_id=${tenantEmFoco()}`,
    { method: "POST", headers: authHeaders() }
  );
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao reativar aluno`);
  return resp.json();
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
  /** O número que a escola usa: mural, recados e chamada de eventual. */
  telefone: string;
  cpf: string;
  /** CPF já pontuado pelo back-end — a tela não formata nada. */
  cpf_formatado: string;
  data_nascimento: string;
  matricula: string;
  endereco: string;
  /** Emergência. **Não** recebe disparo — a tela diz isso em texto. */
  telefone_2: string;
  email: string;
  educacao_fisica: boolean;
  /** `false` = eventual: entra na lista de quem cobre falta (§I1). */
  titular: boolean;
  tem_acesso: boolean;
}

/** Campos do cadastro funcional, na mesma forma que a API recebe. */
export interface DadosProfessor {
  cpf: string;
  data_nascimento: string;
  matricula: string;
  endereco: string;
  telefone_2: string;
  email: string;
  educacao_fisica: boolean;
  titular: boolean;
}

export const DADOS_PROFESSOR_VAZIO: DadosProfessor = {
  cpf: "",
  data_nascimento: "",
  matricula: "",
  endereco: "",
  telefone_2: "",
  email: "",
  educacao_fisica: false,
  titular: true,
};

export async function listarProfessores(): Promise<Professor[]> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/professores/tenant/${tenantEmFoco()}`,
    { headers: authHeaders() }
  );
  return jsonOuErro(resp, "listar professores");
}

/** Eventuais com telefone — a lista de quem a secretaria pode chamar numa falta (§I1). */
export async function listarEventuaisDisponiveis(): Promise<Professor[]> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/professores/tenant/${tenantEmFoco()}/eventuais`,
    { headers: authHeaders() }
  );
  return jsonOuErro(resp, "listar eventuais");
}

export async function cadastrarProfessor(
  nome: string,
  telefone: string,
  senha = "",
  dados: DadosProfessor = DADOS_PROFESSOR_VAZIO
): Promise<Professor> {
  const resp = await apiFetch(`${API_URL}/api/admin/professores`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), nome, telefone, senha, ...dados }),
  });
  return jsonOuErro(resp, "cadastrar professor");
}

export async function atualizarProfessor(
  professorId: string,
  nome: string,
  telefone: string,
  // `undefined` mantém a senha atual; "" limpa o acesso; texto define nova senha.
  senha?: string,
  dados: DadosProfessor = DADOS_PROFESSOR_VAZIO
): Promise<Professor> {
  const resp = await apiFetch(`${API_URL}/api/admin/professores/${professorId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      tenant_id: tenantEmFoco(),
      nome,
      telefone,
      senha: senha ?? null,
      ...dados,
    }),
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
  /** Indexado no RAG? Desativar tira do bot sem apagar o texto. */
  ativo: boolean;
  /** Só vem preenchido no detalhe (`obterConhecimento`), não na listagem. */
  conteudo: string;
  criado_em: string;
  atualizado_em: string | null;
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

export async function obterConhecimento(fonteId: string): Promise<FonteConhecimento> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/conhecimento/${fonteId}?tenant_id=${tenantEmFoco()}`,
    { headers: authHeaders() }
  );
  return jsonOuErro(resp, "carregar documento");
}

export async function atualizarConhecimento(
  fonteId: string,
  nome: string,
  conteudo: string,
  tipo: string,
  ativo: boolean
): Promise<FonteConhecimento> {
  const resp = await apiFetch(`${API_URL}/api/admin/conhecimento/${fonteId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), nome, conteudo, tipo, ativo }),
  });
  return jsonOuErro(resp, "salvar documento");
}

/** Tira do RAG (ou devolve) sem apagar o texto — a via do admin da escola. */
export async function definirAtivoConhecimento(
  fonteId: string,
  ativo: boolean
): Promise<FonteConhecimento> {
  const resp = await apiFetch(`${API_URL}/api/admin/conhecimento/${fonteId}/ativo`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), ativo }),
  });
  return jsonOuErro(resp, "alterar a indexação do documento");
}

/** Apagar é irreversível e **exige super admin** — o back-end recusa os demais com 403. */
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

// ============================ ONDA 1 (Rosa Cury) =========================== //

// --------------------- C1 · respostas rápidas ("atalhos") ----------------- //
export interface RespostaRapida {
  id: string;
  chave: string;
  conteudo: string;
  ativo: boolean;
  fonte_id: string | null;
  atualizado_em: string | null;
}

export async function listarRespostasRapidas(): Promise<RespostaRapida[]> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/respostas-rapidas/tenant/${tenantEmFoco()}`,
    { headers: authHeaders() }
  );
  return jsonOuErro(resp, "listar respostas rápidas");
}

export async function criarRespostaRapida(
  chave: string,
  conteudo: string,
  ativo = true
): Promise<RespostaRapida> {
  const resp = await apiFetch(`${API_URL}/api/admin/respostas-rapidas`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), chave, conteudo, ativo }),
  });
  return jsonOuErro(resp, "criar resposta rápida");
}

export async function atualizarRespostaRapida(
  id: string,
  chave: string,
  conteudo: string,
  ativo: boolean
): Promise<RespostaRapida> {
  const resp = await apiFetch(`${API_URL}/api/admin/respostas-rapidas/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), chave, conteudo, ativo }),
  });
  return jsonOuErro(resp, "atualizar resposta rápida");
}

export async function removerRespostaRapida(id: string): Promise<void> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/respostas-rapidas/${id}?tenant_id=${tenantEmFoco()}`,
    { method: "DELETE", headers: authHeaders() }
  );
  if (!resp.ok && resp.status !== 204) throw await erroDe(resp, "remover resposta rápida");
}

// --------------------- C2 · avisos temporizados --------------------------- //
export interface AvisoTemporizado {
  id: string;
  mensagem: string;
  ativo: boolean;
  inicia_em: string | null;
  expira_em: string | null;
  vigente: boolean;
  atualizado_em: string | null;
}

export async function listarAvisos(): Promise<AvisoTemporizado[]> {
  const resp = await apiFetch(`${API_URL}/api/admin/avisos/tenant/${tenantEmFoco()}`, {
    headers: authHeaders(),
  });
  return jsonOuErro(resp, "listar avisos");
}

export async function criarAviso(
  mensagem: string,
  ativo: boolean,
  iniciaEm: string | null,
  expiraEm: string | null
): Promise<AvisoTemporizado> {
  const resp = await apiFetch(`${API_URL}/api/admin/avisos`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      tenant_id: tenantEmFoco(),
      mensagem,
      ativo,
      inicia_em: iniciaEm,
      expira_em: expiraEm,
    }),
  });
  return jsonOuErro(resp, "criar aviso");
}

export async function atualizarAviso(
  id: string,
  mensagem: string,
  ativo: boolean,
  iniciaEm: string | null,
  expiraEm: string | null
): Promise<AvisoTemporizado> {
  const resp = await apiFetch(`${API_URL}/api/admin/avisos/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      tenant_id: tenantEmFoco(),
      mensagem,
      ativo,
      inicia_em: iniciaEm,
      expira_em: expiraEm,
    }),
  });
  return jsonOuErro(resp, "atualizar aviso");
}

export async function removerAviso(id: string): Promise<void> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/avisos/${id}?tenant_id=${tenantEmFoco()}`,
    { method: "DELETE", headers: authHeaders() }
  );
  if (!resp.ok && resp.status !== 204) throw await erroDe(resp, "remover aviso");
}

// --------------------- B1 · fila de impressão ----------------------------- //
export type StatusImpressao = "pendente" | "em_processo" | "concluida" | "cancelada";

export interface Impressao {
  id: string;
  professor_id: string | null;
  professor_nome: string;
  arquivo_nome: string;
  arquivo_url: string;
  copias: number;
  colorido: boolean;
  frente_verso: boolean;
  observacao: string;
  status: StatusImpressao;
  criado_em: string;
  atualizado_em: string | null;
}

export async function listarFilaImpressao(status?: StatusImpressao): Promise<Impressao[]> {
  const qs = status ? `?status_filtro=${status}` : "";
  const resp = await apiFetch(
    `${API_URL}/api/admin/impressao/tenant/${tenantEmFoco()}${qs}`,
    { headers: authHeaders() }
  );
  return jsonOuErro(resp, "listar fila de impressão");
}

export async function criarImpressao(dados: {
  arquivo_nome: string;
  professor_id?: string | null;
  arquivo_url?: string;
  copias: number;
  colorido: boolean;
  frente_verso: boolean;
  observacao?: string;
}): Promise<Impressao> {
  const resp = await apiFetch(`${API_URL}/api/admin/impressao`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), ...dados }),
  });
  return jsonOuErro(resp, "criar solicitação de impressão");
}

export async function atualizarStatusImpressao(
  id: string,
  status: StatusImpressao
): Promise<Impressao> {
  const resp = await apiFetch(`${API_URL}/api/admin/impressao/${id}/status`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), status }),
  });
  return jsonOuErro(resp, "atualizar status da impressão");
}

export async function removerImpressao(id: string): Promise<void> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/impressao/${id}?tenant_id=${tenantEmFoco()}`,
    { method: "DELETE", headers: authHeaders() }
  );
  if (!resp.ok && resp.status !== 204) throw await erroDe(resp, "remover solicitação");
}

// --------------------- A1 · mural do professor (secretaria) --------------- //
export interface RecadoResumo {
  id: string;
  titulo: string;
  corpo: string;
  autor_nome: string;
  criado_em: string;
  total_professores: number;
  total_lidos: number;
  total_nao_lidos: number;
}

export interface LeitorRecado {
  professor_id: string;
  nome: string;
  telefone: string;
  lido_em: string | null;
}

export interface RecadoStatusLeitura {
  id: string;
  titulo: string;
  corpo: string;
  criado_em: string;
  lidos: LeitorRecado[];
  nao_lidos: LeitorRecado[];
}

export async function listarRecados(): Promise<RecadoResumo[]> {
  const resp = await apiFetch(`${API_URL}/api/admin/recados/tenant/${tenantEmFoco()}`, {
    headers: authHeaders(),
  });
  return jsonOuErro(resp, "listar recados");
}

export async function publicarRecado(titulo: string, corpo: string): Promise<RecadoResumo> {
  const resp = await apiFetch(`${API_URL}/api/admin/recados`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), titulo, corpo }),
  });
  return jsonOuErro(resp, "publicar recado");
}

export async function statusLeituraRecado(id: string): Promise<RecadoStatusLeitura> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/recados/${id}/leitura?tenant_id=${tenantEmFoco()}`,
    { headers: authHeaders() }
  );
  return jsonOuErro(resp, "carregar status de leitura");
}

export async function renotificarRecado(id: string): Promise<{ avisados: number }> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/recados/${id}/renotificar?tenant_id=${tenantEmFoco()}`,
    { method: "POST", headers: authHeaders() }
  );
  return jsonOuErro(resp, "re-notificar professores");
}

export async function removerRecado(id: string): Promise<void> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/recados/${id}?tenant_id=${tenantEmFoco()}`,
    { method: "DELETE", headers: authHeaders() }
  );
  if (!resp.ok && resp.status !== 204) throw await erroDe(resp, "remover recado");
}

// ========================================================================== //
// Onda 2 · A2/A4 — canal interno professor → secretaria/gestão/pedagógico
// ========================================================================== //
export type CategoriaSolicitacao = "secretaria" | "gestao" | "pedagogico";
export type StatusSolicitacaoInterna =
  | "aberta"
  | "em_andamento"
  | "resolvida"
  | "cancelada";

export interface SolicitacaoInterna {
  id: string;
  professor_id: string | null;
  professor_nome: string;
  assunto: string;
  corpo: string;
  categoria: CategoriaSolicitacao;
  status: StatusSolicitacaoInterna;
  resposta: string;
  respondido_em: string | null;
  criado_em: string;
  atualizado_em: string;
}

export async function listarSolicitacoesInternas(filtros?: {
  categoria?: CategoriaSolicitacao;
  status?: StatusSolicitacaoInterna;
}): Promise<SolicitacaoInterna[]> {
  const params = new URLSearchParams();
  if (filtros?.categoria) params.set("categoria", filtros.categoria);
  if (filtros?.status) params.set("status_filtro", filtros.status);
  const qs = params.toString() ? `?${params.toString()}` : "";
  const resp = await apiFetch(
    `${API_URL}/api/admin/solicitacoes-internas/tenant/${tenantEmFoco()}${qs}`,
    { headers: authHeaders() }
  );
  return jsonOuErro(resp, "listar solicitações internas");
}

export async function abrirSolicitacaoInterna(dados: {
  assunto: string;
  corpo: string;
  professor_id?: string | null;
  categoria: CategoriaSolicitacao;
}): Promise<SolicitacaoInterna> {
  const resp = await apiFetch(`${API_URL}/api/admin/solicitacoes-internas`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), ...dados }),
  });
  return jsonOuErro(resp, "abrir solicitação interna");
}

export async function responderSolicitacaoInterna(
  id: string,
  resposta: string,
  notificar: boolean
): Promise<SolicitacaoInterna> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/solicitacoes-internas/${id}/responder`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ tenant_id: tenantEmFoco(), resposta, notificar }),
    }
  );
  return jsonOuErro(resp, "responder solicitação interna");
}

export async function atualizarStatusSolicitacaoInterna(
  id: string,
  status: StatusSolicitacaoInterna
): Promise<SolicitacaoInterna> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/solicitacoes-internas/${id}/status`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ tenant_id: tenantEmFoco(), status }),
    }
  );
  return jsonOuErro(resp, "atualizar status da solicitação");
}

export async function removerSolicitacaoInterna(id: string): Promise<void> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/solicitacoes-internas/${id}?tenant_id=${tenantEmFoco()}`,
    { method: "DELETE", headers: authHeaders() }
  );
  if (!resp.ok && resp.status !== 204) throw await erroDe(resp, "remover solicitação");
}

// ========================================================================== //
// Onda 2 · B2 — cota e relatório de impressões por professor
// ========================================================================== //
export interface CotaImpressao {
  id: string;
  professor_id: string;
  professor_nome: string;
  limite_mensal: number;
  ilimitado: boolean;
}

export interface LinhaRelatorioImpressao {
  professor_id: string | null;
  professor_nome: string;
  total_solicitacoes: number;
  total_copias: number;
  limite_mensal: number;
  ilimitado: boolean;
  excedeu: boolean;
  restante: number;
}

export interface RelatorioImpressao {
  competencia: string;
  total_copias: number;
  total_solicitacoes: number;
  linhas: LinhaRelatorioImpressao[];
}

export async function listarCotasImpressao(): Promise<CotaImpressao[]> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/impressao/cotas/tenant/${tenantEmFoco()}`,
    { headers: authHeaders() }
  );
  return jsonOuErro(resp, "listar cotas de impressão");
}

export async function definirCotaImpressao(
  professorId: string,
  limiteMensal: number
): Promise<CotaImpressao> {
  const resp = await apiFetch(`${API_URL}/api/admin/impressao/cotas`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      tenant_id: tenantEmFoco(),
      professor_id: professorId,
      limite_mensal: limiteMensal,
    }),
  });
  return jsonOuErro(resp, "definir cota de impressão");
}

export async function removerCotaImpressao(professorId: string): Promise<void> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/impressao/cotas/${professorId}?tenant_id=${tenantEmFoco()}`,
    { method: "DELETE", headers: authHeaders() }
  );
  if (!resp.ok && resp.status !== 204) throw await erroDe(resp, "remover cota");
}

export async function relatorioImpressao(
  competencia: string
): Promise<RelatorioImpressao> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/impressao/relatorio/tenant/${tenantEmFoco()}?competencia=${competencia}`,
    { headers: authHeaders() }
  );
  return jsonOuErro(resp, "gerar relatório de impressão");
}

// ========================================================================== //
// Onda 2 · F1 — progressão de série e ciclo de vida do responsável
// ========================================================================== //
export interface ResultadoPromocao {
  origem_sala_id: string;
  origem_sala_nome: string;
  destino_sala_id: string | null;
  destino_sala_nome: string;
  alunos_promovidos: number;
  alunos_formados: number;
}

export interface ResponsavelInativado {
  contato_id: string;
  nome: string;
  telefone: string;
}

export async function promoverTurmas(
  promocoes: { origem_sala_id: string; destino_sala_id: string | null }[]
): Promise<ResultadoPromocao[]> {
  const resp = await apiFetch(`${API_URL}/api/admin/progressao/promover`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), promocoes }),
  });
  return jsonOuErro(resp, "promover turmas");
}

export interface SincronizacaoResponsaveis {
  inativados: ResponsavelInativado[];
  reativados: ResponsavelInativado[];
}

/**
 * **Reprocessamento** da situação dos responsáveis na escola inteira.
 *
 * A sincronização acontece sozinha na promoção de turmas e ao desativar/reativar um aluno.
 * Esta rota serve para conferir tudo depois de uma importação em massa ou de um ajuste
 * feito direto no banco. A URL manteve o nome antigo, mas a operação é bidirecional.
 */
export async function sincronizarResponsaveis(): Promise<SincronizacaoResponsaveis> {
  const resp = await apiFetch(`${API_URL}/api/admin/progressao/inativar-responsaveis`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco() }),
  });
  return jsonOuErro(resp, "sincronizar responsáveis");
}

// --------------------- postura de segurança (super admin) ------------------ //
export type StatusMedida = "ativa" | "atencao" | "pendente" | "nao_aplicavel";

export interface MedidaSeguranca {
  chave: string;
  titulo: string;
  categoria: string;
  descricao: string;
  risco: string;
  status: StatusMedida;
  detalhe: string;
  referencia: string;
}

export interface ItemChecklist {
  numero: number;
  titulo: string;
  exigencia: string;
  status: StatusMedida;
  situacao: string;
  medidas_relacionadas: string[];
}

export interface PosturaSeguranca {
  medidas: MedidaSeguranca[];
  total_ativas: number;
  total_atencao: number;
  total_pendentes: number;
  checklist: ItemChecklist[];
  checklist_fonte: string;
  checklist_ok: number;
  checklist_pendentes: number;
  pronto_para_producao: boolean;
  ambiente: string;
  canal: string;
  gerado_em: string;
}

export async function obterPosturaSeguranca(): Promise<PosturaSeguranca> {
  const resp = await apiFetch(`${API_URL}/api/admin/seguranca`, { headers: authHeaders() });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao carregar a postura de segurança`);
  return resp.json();
}

// --------------------------------------------------------------------------- //
// Logs da aplicação (§16) — exclusivo do super admin
// --------------------------------------------------------------------------- //
export type NivelLog = "INFO" | "WARNING" | "ERROR" | "CRITICAL";

export interface RegistroLog {
  id: string;
  criado_em: string;
  nivel: NivelLog;
  logger: string;
  mensagem: string;
  correlacao_id: string;
  rota: string;
  metodo: string;
  status_code: number | null;
  duracao_ms: number | null;
  tenant_id: string | null;
  excecao: string;
  metadados: Record<string, unknown>;
}

export interface PaginaMeta {
  pagina: number;
  por_pagina: number;
  total: number;
  total_paginas: number;
}

/** Envelope das listagens paginadas — o mesmo formato em todas as telas. */
export interface Pagina<T> {
  itens: T[];
  meta: PaginaMeta;
}

/** Monta a query string de paginação; omitir = usa o padrão do back-end (10). */
function qsPaginacao(pagina?: number, porPagina?: number): string {
  const params = new URLSearchParams();
  if (pagina) params.set("pagina", String(pagina));
  if (porPagina) params.set("por_pagina", String(porPagina));
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export interface LogsPagina {
  itens: RegistroLog[];
  meta: PaginaMeta;
  loggers: string[];
}

export interface Contagem {
  rotulo: string;
  quantidade: number;
}

export interface ResumoLogs {
  janela_horas: number;
  total: number;
  erros: number;
  alertas: number;
  requisicoes: number;
  duracao_media_ms: number;
  duracao_p95_ms: number;
  taxa_erro_percentual: number;
  saudavel: boolean;
  atendimentos_concluidos: number;
  atendimentos_em_andamento: number;
  atendimentos_falhos: number;
  rotas_mais_lentas: Contagem[];
  erros_mais_comuns: Contagem[];
}

export interface AtendimentoInbound {
  chave: string;
  status: string;
  origem: string;
  resumo: string;
  tenant_id: string | null;
  tenant_nome: string;
  criado_em: string;
  atualizado_em: string;
}

export interface FiltroLogs {
  nivel?: string;
  logger_nome?: string;
  correlacao_id?: string;
  busca?: string;
  apenas_falhas?: boolean;
  pagina?: number;
  por_pagina?: number;
}

export async function listarLogs(filtro: FiltroLogs = {}): Promise<LogsPagina> {
  const params = new URLSearchParams();
  for (const [chave, valor] of Object.entries(filtro)) {
    if (valor !== undefined && valor !== "" && valor !== false) params.set(chave, String(valor));
  }
  const resp = await apiFetch(`${API_URL}/api/admin/logs?${params.toString()}`, {
    headers: authHeaders(),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao carregar os logs`);
  return resp.json();
}

export async function obterResumoLogs(janelaHoras = 24): Promise<ResumoLogs> {
  const resp = await apiFetch(`${API_URL}/api/admin/logs/resumo?janela_horas=${janelaHoras}`, {
    headers: authHeaders(),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao carregar o resumo`);
  return resp.json();
}

export async function listarAtendimentosInbound(
  status = "",
  limite = 30,
): Promise<AtendimentoInbound[]> {
  const params = new URLSearchParams({ limite: String(limite) });
  if (status) params.set("status", status);
  const resp = await apiFetch(`${API_URL}/api/admin/logs/atendimentos?${params.toString()}`, {
    headers: authHeaders(),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao carregar os atendimentos`);
  return resp.json();
}

// --------------------------------------------------------------------------- //
// Atendimento humano — a fila da secretaria (§6j)
// --------------------------------------------------------------------------- //
export type StatusAtendimento =
  | "oferecido"
  | "aberto"
  | "em_atendimento"
  | "resolvido"
  | "descartado";

export interface Atendimento {
  id: string;
  conversa_id: string;
  contato: string;
  contato_nome: string;
  motivo: string;
  status: StatusAtendimento;
  fora_expediente: boolean;
  atendente_id: string | null;
  atendente_nome: string;
  minutos_de_espera: number;
  /** Janela de 24h da Meta. Fechada, o texto livre é recusado e só template reabre. */
  janela_aberta: boolean;
  janela_expira_em: string;
  ofereceu_em: string | null;
  confirmado_em: string | null;
  assumido_em: string | null;
  resolvido_em: string | null;
  criado_em: string;
  atualizado_em: string;
}

export interface MensagemAtendimento {
  autor: "usuario" | "bot" | "atendente";
  autor_nome: string;
  texto: string;
  fontes: string[];
  criado_em: string;
}

export interface AtendimentoDetalhe {
  atendimento: Atendimento;
  mensagens: MensagemAtendimento[];
}

export interface AtendimentosPagina {
  itens: Atendimento[];
  meta: PaginaMeta;
}

export async function listarAtendimentos(opcoes: {
  status?: string;
  meus?: boolean;
  pagina?: number;
  porPagina?: number;
} = {}): Promise<AtendimentosPagina> {
  const params = new URLSearchParams({
    pagina: String(opcoes.pagina ?? 1),
    por_pagina: String(opcoes.porPagina ?? 25),
  });
  if (opcoes.status) params.set("status", opcoes.status);
  if (opcoes.meus) params.set("meus", "true");
  const resp = await apiFetch(
    `${API_URL}/api/admin/atendimentos/tenant/${tenantEmFoco()}?${params.toString()}`,
    { headers: authHeaders() },
  );
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao carregar a fila`);
  return resp.json();
}

/** Contador do badge. Consultado em polling, então devolve só o número. */
export async function contarAtendimentosPendentes(): Promise<number> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/atendimentos/tenant/${tenantEmFoco()}/pendentes`,
    { headers: authHeaders() },
  );
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao contar pendentes`);
  const dados = (await resp.json()) as { pendentes: number };
  return dados.pendentes;
}

export async function contarDocumentosPendentes(): Promise<number> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/documentos/tenant/${tenantEmFoco()}/pendentes`,
    { headers: authHeaders() },
  );
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao contar documentos`);
  const dados = (await resp.json()) as { pendentes: number };
  return dados.pendentes;
}

export async function obterAtendimento(id: string): Promise<AtendimentoDetalhe> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/atendimentos/${id}?tenant_id=${tenantEmFoco()}`,
    { headers: authHeaders() },
  );
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao abrir o atendimento`);
  return resp.json();
}

async function acaoAtendimento(
  id: string,
  acao: "assumir" | "resolver" | "reabrir",
  extra = "",
): Promise<Atendimento> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/atendimentos/${id}/${acao}?tenant_id=${tenantEmFoco()}${extra}`,
    { method: "POST", headers: authHeaders() },
  );
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao ${acao} o atendimento`);
  return resp.json();
}

export const assumirAtendimento = (id: string) => acaoAtendimento(id, "assumir");
export const resolverAtendimento = (id: string) => acaoAtendimento(id, "resolver");
export const reabrirAtendimento = (id: string, liberar = false) =>
  acaoAtendimento(id, "reabrir", liberar ? "&liberar=true" : "");

export async function responderAtendimento(id: string, texto: string): Promise<Atendimento> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/atendimentos/${id}/responder?tenant_id=${tenantEmFoco()}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ texto }),
    },
  );
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao responder`);
  return resp.json();
}

// --------------------------------------------------------------------------- //
// Usuários da escola (a equipe da secretaria que atende)
// --------------------------------------------------------------------------- //
export async function listarUsuarios(): Promise<Usuario[]> {
  const resp = await apiFetch(`${API_URL}/api/admin/usuarios`, { headers: authHeaders() });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao listar usuários`);
  return resp.json();
}

export async function criarUsuario(dados: {
  nome: string;
  email: string;
  senha: string;
  cargo: Cargo;
  telefone?: string;
  endereco?: string;
  turno?: Turno | "";
}): Promise<Usuario> {
  const resp = await apiFetch(`${API_URL}/api/admin/usuarios`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    // `papel` vai como tenant_admin, mas quem manda é o `cargo`: o back-end deriva o
    // papel dele (secretaria não administra), então não há como criar uma secretaria
    // com acesso de admin por engano.
    body: JSON.stringify({ ...dados, papel: "tenant_admin", tenant_id: tenantEmFoco() }),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao criar usuário`);
  return resp.json();
}

export async function atualizarUsuario(
  id: string,
  dados: {
    nome?: string;
    senha?: string;
    ativo?: boolean;
    cargo?: Cargo;
    telefone?: string;
    endereco?: string;
    turno?: Turno | "";
  },
): Promise<Usuario> {
  const resp = await apiFetch(`${API_URL}/api/admin/usuarios/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(dados),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao atualizar usuário`);
  return resp.json();
}

// --------------------------------------------------------------------------- //
// Documentos que os responsáveis enviam pelo WhatsApp (§6k)
// --------------------------------------------------------------------------- //
export type CategoriaDocumento = "matricula" | "atestado" | "comprovante" | "outro";
export type StatusDocumento = "recebido" | "processado" | "descartado";

export interface DocumentoRecebido {
  id: string;
  conversa_id: string;
  contato: string;
  contato_nome: string;
  nome_arquivo: string;
  mime: string;
  tamanho: number;
  tamanho_legivel: string;
  eh_imagem: boolean;
  observacao: string;
  categoria: CategoriaDocumento;
  /** Palpite da heurística pela legenda — sugestão, não decisão. */
  categoria_sugerida: CategoriaDocumento | null;
  status: StatusDocumento;
  aluno_id: string | null;
  aluno_nome: string;
  atendimento_id: string | null;
  /** Prazo de retenção (LGPD): depois disso o arquivo é apagado. */
  expira_em: string | null;
  processado_em: string | null;
  criado_em: string;
}

export interface DocumentosPagina {
  itens: DocumentoRecebido[];
  meta: PaginaMeta;
}

export async function listarDocumentos(opcoes: {
  categoria?: string;
  status?: string;
  alunoId?: string;
  pagina?: number;
  porPagina?: number;
} = {}): Promise<DocumentosPagina> {
  const params = new URLSearchParams({
    pagina: String(opcoes.pagina ?? 1),
    por_pagina: String(opcoes.porPagina ?? 25),
  });
  if (opcoes.categoria) params.set("categoria", opcoes.categoria);
  if (opcoes.status) params.set("status", opcoes.status);
  if (opcoes.alunoId) params.set("aluno_id", opcoes.alunoId);
  const resp = await apiFetch(
    `${API_URL}/api/admin/documentos/tenant/${tenantEmFoco()}?${params.toString()}`,
    { headers: authHeaders() },
  );
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao listar documentos`);
  return resp.json();
}

/**
 * Baixa o arquivo e devolve um object URL temporário.
 *
 * Não há link direto de propósito: o conteúdo é dado sensível de menor e só sai pela API
 * autenticada. Quem chama **precisa** dar `URL.revokeObjectURL` depois — senão os bytes
 * ficam na memória da aba.
 */
export async function baixarDocumento(id: string): Promise<{ url: string; nome: string }> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/documentos/${id}/arquivo?tenant_id=${tenantEmFoco()}`,
    { headers: authHeaders() },
  );
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao baixar o arquivo`);
  const blob = await resp.blob();
  const disposicao = resp.headers.get("Content-Disposition") ?? "";
  const nome = /filename="?([^"]+)"?/.exec(disposicao)?.[1] ?? `documento-${id}`;
  return { url: URL.createObjectURL(blob), nome };
}

export async function classificarDocumento(
  id: string,
  dados: {
    categoria?: CategoriaDocumento;
    status?: StatusDocumento;
    aluno_id?: string | null;
    observacao?: string;
  },
): Promise<DocumentoRecebido> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/documentos/${id}?tenant_id=${tenantEmFoco()}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(dados),
    },
  );
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao classificar`);
  return resp.json();
}

export async function expurgarDocumentos(): Promise<{ removidos: number; falhas: number }> {
  const resp = await apiFetch(`${API_URL}/api/admin/documentos/expurgar`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!resp.ok) throw await erroDe(resp, `Erro ${resp.status} ao expurgar`);
  return resp.json();
}

// --------------------------------------------------------------------------- //
// Ficha de matrícula (§D1/D2)
// --------------------------------------------------------------------------- //
/**
 * A ficha é um mapa de campos livre no back-end (JSON `conteudo`), de propósito: cada
 * escola tem uma variação da ficha física, e `dados_extra` acomoda o que não couber.
 * Aqui os campos são tipados como `string | boolean` porque é o que a tela manipula.
 */
export type CamposFicha = Record<string, string | boolean>;

export interface Ficha {
  aluno_id: string;
  aluno_nome: string;
  campos: CamposFicha;
  atualizado_em: string;
}

/** Devolve `null` quando o aluno ainda não tem ficha — é a "ficha pendente" do painel. */
export async function obterFicha(alunoId: string): Promise<Ficha | null> {
  const resp = await apiFetch(
    `${API_URL}/api/admin/fichas/aluno/${alunoId}?tenant_id=${tenantEmFoco()}`,
    { headers: authHeaders() }
  );
  if (resp.status === 404) return null;
  return jsonOuErro(resp, "carregar a ficha");
}

export async function salvarFicha(alunoId: string, campos: CamposFicha): Promise<Ficha> {
  const resp = await apiFetch(`${API_URL}/api/admin/fichas`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tenant_id: tenantEmFoco(), aluno_id: alunoId, campos }),
  });
  return jsonOuErro(resp, "salvar a ficha");
}
