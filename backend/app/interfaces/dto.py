"""DTOs de entrada/saída da API (Pydantic)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MensagemEntrada(BaseModel):
    tenant_id: UUID
    contato: str = Field(..., examples=["+5511999998888"])
    texto: str


class DocumentoSaida(BaseModel):
    nome: str
    categoria: str
    url: str


class MensagemSaida(BaseModel):
    texto: str
    fontes: list[str] = []
    documentos: list[DocumentoSaida] = []


class DestinatarioEntrada(BaseModel):
    contato: str
    parametros: list[str] = []


class BroadcastEntrada(BaseModel):
    tenant_id: UUID
    template_id: UUID
    titulo: str
    destinatarios: list[DestinatarioEntrada]


class BroadcastSaida(BaseModel):
    broadcast_id: UUID
    status: str
    enviados: int
    falhas: int
    bloqueados_por_limite: int
    restante_cota: int


class QuotaSaida(BaseModel):
    tenant_id: UUID
    dia: str
    limite_diario: int
    enviados: int
    restante: int


# --------------------------------------------------------------------------- #
# Administração e grupos
# --------------------------------------------------------------------------- #
class LoginEntrada(BaseModel):
    email: str
    senha: str


class UsuarioSaida(BaseModel):
    id: UUID
    nome: str
    email: str
    papel: str
    tenant_id: UUID | None = None


class TokenSaida(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_em: int  # validade do token em segundos
    usuario: UsuarioSaida


class CriarUsuarioEntrada(BaseModel):
    nome: str
    email: str
    senha: str
    papel: str = Field(..., examples=["tenant_admin", "super_admin"])
    tenant_id: UUID | None = None


class GrupoEntrada(BaseModel):
    tenant_id: UUID
    nome: str
    descricao: str = ""


class ContatoSaida(BaseModel):
    id: UUID
    nome: str
    telefone: str


class GrupoSaida(BaseModel):
    id: UUID
    nome: str
    descricao: str
    total_membros: int
    membros: list[ContatoSaida] = []


class ContatoEntrada(BaseModel):
    tenant_id: UUID
    nome: str
    telefone: str = Field(..., examples=["+5511999990000"])


class EnvioGrupoEntrada(BaseModel):
    tenant_id: UUID
    template_id: UUID
    titulo: str
    mensagem: str


class EnvioGrupoSaida(BaseModel):
    grupo_id: UUID
    total_contatos: int
    broadcast: BroadcastSaida


# --------------------------------------------------------------------------- #
# Escolas (tenants) — CRUD do super admin
# --------------------------------------------------------------------------- #
class EscolaEntrada(BaseModel):
    nome: str
    # Opcional: se vazio, é derivado do nome.
    slug: str = ""


class LicencaSaida(BaseModel):
    """Estado de licenciamento/cobrança/bloqueio de uma escola."""

    status: str  # "ativo" | "bloqueado"
    motivo_bloqueio: str = ""
    bloqueado_em: datetime | None = None
    plano: str  # "mensal" | "anual"
    licenca_expira_em: datetime | None = None
    dias_para_expirar: int | None = None
    licenca_expirada: bool = False


class EscolaSaida(BaseModel):
    id: UUID
    nome: str
    slug: str
    criado_em: datetime
    licenca: LicencaSaida


class EscolaResumoSaida(BaseModel):
    id: UUID
    nome: str
    slug: str
    criado_em: datetime
    total_conversas: int
    total_contatos: int
    total_broadcasts: int
    licenca: LicencaSaida


class BloqueioEntrada(BaseModel):
    motivo: str = Field(..., examples=["Inadimplência: mensalidade de junho/2026 em aberto."])


class LicencaEntrada(BaseModel):
    plano: str = Field("mensal", examples=["mensal", "anual"])
    licenca_expira_em: datetime | None = None


class AvisoLicencaSaida(BaseModel):
    tenant_id: UUID
    nome: str
    dias_para_expirar: int
    destinatarios: list[str] = []


# --------------------------------------------------------------------------- #
# Visualização de conversas (inbound) e broadcasts (outbound) da escola
# --------------------------------------------------------------------------- #
class ConversaResumoSaida(BaseModel):
    id: UUID
    contato: str
    criado_em: datetime
    total_mensagens: int
    ultima_mensagem: str
    ultima_em: datetime | None = None


class MensagemConversaSaida(BaseModel):
    id: UUID
    autor: str  # "usuario" | "bot"
    texto: str
    fontes: list[str] = []
    criado_em: datetime


class ConversaDetalheSaida(BaseModel):
    id: UUID
    contato: str
    criado_em: datetime
    mensagens: list[MensagemConversaSaida] = []


class BroadcastResumoSaida(BaseModel):
    id: UUID
    titulo: str
    status: str
    template_nome: str = ""
    criado_em: datetime
    agendado_para: datetime | None = None
    total_destinatarios: int
    por_status: dict[str, int] = {}


class DestinatarioBroadcastSaida(BaseModel):
    contato: str
    nome: str = ""  # nome do responsável, se cadastrado
    status: str
    atualizado_em: datetime | None = None


class BroadcastDetalheSaida(BaseModel):
    id: UUID
    titulo: str
    status: str
    template_nome: str = ""
    criado_em: datetime
    agendado_para: datetime | None = None
    total_destinatarios: int
    por_status: dict[str, int] = {}
    destinatarios: list[DestinatarioBroadcastSaida] = []


class NaoEntregaSaida(BaseModel):
    """Um responsável que (provavelmente) não recebeu o aviso de um broadcast."""

    contato: str
    nome: str
    status: str
    motivo: str  # "falha_envio" | "sem_confirmacao"
    atualizado_em: datetime | None = None


# --------------------------------------------------------------------------- #
# Auditoria de ações (usuários logados + LLM)
# --------------------------------------------------------------------------- #
class RegistroAuditoriaSaida(BaseModel):
    id: UUID
    tenant_id: UUID | None = None
    ator: str  # "usuario" | "llm" | "sistema"
    ator_id: str = ""
    ator_nome: str = ""
    acao: str
    descricao: str = ""
    metadados: dict = {}
    criado_em: datetime


# --------------------------------------------------------------------------- #
# Pais/responsáveis (CRUD) e salas/turmas
# --------------------------------------------------------------------------- #
class PaiEntrada(BaseModel):
    tenant_id: UUID
    nome: str
    telefone: str = Field(..., examples=["+5511999990000"])
    # Salas às quais já vincular o responsável no cadastro (opcional).
    sala_ids: list[UUID] = []


class PaiAtualizar(BaseModel):
    tenant_id: UUID
    nome: str
    telefone: str = Field(..., examples=["+5511999990000"])


class PaiSaida(BaseModel):
    id: UUID
    nome: str
    telefone: str


class SalaEntrada(BaseModel):
    tenant_id: UUID
    nome: str = Field(..., examples=["4ª série B"])
    descricao: str = ""


class SalaAtualizar(BaseModel):
    tenant_id: UUID
    nome: str = Field(..., examples=["4ª série B"])
    descricao: str = ""


class SalaSaida(BaseModel):
    id: UUID
    nome: str
    descricao: str
    total_pais: int
    pais: list[PaiSaida] = []


class TenantRef(BaseModel):
    """Corpo mínimo para operações que só precisam confirmar o tenant."""

    tenant_id: UUID


class VinculoPaiEntrada(BaseModel):
    tenant_id: UUID
    contato_id: UUID


# --------------------------------------------------------------------------- #
# Alunos (CRUD) — responsáveis N:N, série 1:1
# --------------------------------------------------------------------------- #
class AlunoEntrada(BaseModel):
    tenant_id: UUID
    nome: str
    matricula: str = ""
    # Série/turma (1:1) — obrigatória.
    sala_id: UUID
    # Responsáveis a vincular já no cadastro (opcional).
    responsavel_ids: list[UUID] = []


class AlunoAtualizar(BaseModel):
    tenant_id: UUID
    nome: str
    matricula: str = ""
    sala_id: UUID
    ativo: bool = True


class AlunoSaida(BaseModel):
    id: UUID
    nome: str
    matricula: str
    ativo: bool
    sala_id: UUID
    sala_nome: str = ""
    responsaveis: list[PaiSaida] = []


# --------------------------------------------------------------------------- #
# Cobertura de contatos da turma e notificação ao professor
# --------------------------------------------------------------------------- #
class AlunoResumoSaida(BaseModel):
    id: UUID
    nome: str
    matricula: str = ""


class CoberturaSalaSaida(BaseModel):
    sala_id: UUID
    sala_nome: str
    total_alunos: int
    total_sem_contato: int
    alunos_sem_contato: list[AlunoResumoSaida] = []


class NotificarProfessorEntrada(BaseModel):
    tenant_id: UUID
    # WhatsApp do professor que vai coletar os contatos faltantes.
    telefone: str = Field(..., examples=["+5511999990000"])
    # Mensagem opcional acrescentada antes do aviso automático.
    mensagem: str = ""


class NotificarProfessorSaida(BaseModel):
    enviado: bool
    id_externo: str
    telefone: str
    total_sem_contato: int
    cobertura: CoberturaSalaSaida


# --------------------------------------------------------------------------- #
# Base de conhecimento (RAG) e system prompt por tenant
# --------------------------------------------------------------------------- #
class DocumentoConhecimentoEntrada(BaseModel):
    tenant_id: UUID
    nome: str = Field(..., examples=["Manual de procedimentos 2026"])
    conteudo: str
    # "procedimento" | "aviso" | "faq"
    tipo: str = "procedimento"


class FonteConhecimentoSaida(BaseModel):
    id: UUID
    nome: str
    tipo: str
    total_trechos: int
    criado_em: datetime


class PromptTenantEntrada(BaseModel):
    tenant_id: UUID
    conteudo: str = ""


class PromptTenantSaida(BaseModel):
    tenant_id: UUID
    conteudo: str
    atualizado_em: datetime | None = None
