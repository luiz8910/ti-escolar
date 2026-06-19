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


class EscolaSaida(BaseModel):
    id: UUID
    nome: str
    slug: str
    criado_em: datetime


class EscolaResumoSaida(BaseModel):
    id: UUID
    nome: str
    slug: str
    criado_em: datetime
    total_conversas: int
    total_contatos: int
    total_broadcasts: int


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
    criado_em: datetime
    agendado_para: datetime | None = None
    total_destinatarios: int
    por_status: dict[str, int] = {}


class NaoEntregaSaida(BaseModel):
    """Um responsável que (provavelmente) não recebeu o aviso de um broadcast."""

    contato: str
    nome: str
    status: str
    motivo: str  # "falha_envio" | "sem_confirmacao"
    atualizado_em: datetime | None = None


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
