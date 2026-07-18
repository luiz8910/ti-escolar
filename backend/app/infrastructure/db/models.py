"""Modelos ORM (SQLAlchemy 2.0). Camada de infraestrutura — não vaza para o domínio."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import get_settings

_DIM = get_settings().embedding_dim


class Base(DeclarativeBase):
    pass


class TenantORM(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    criado_em: Mapped[datetime] = mapped_column()
    # Número de WhatsApp (E.164) da escola; vazio = usa o número padrão do canal.
    whatsapp_numero: Mapped[str] = mapped_column(
        String(30), default="", server_default="", index=True
    )
    # Telefone de contato (E.164) público da escola — informativo (secretaria). Sem índice
    # nem unicidade: não roteia mensagens.
    telefone_contato: Mapped[str] = mapped_column(String(30), default="", server_default="")
    # Licenciamento / cobrança / bloqueio.
    status: Mapped[str] = mapped_column(String(20), default="ativo", server_default="ativo")
    motivo_bloqueio: Mapped[str] = mapped_column(Text, default="", server_default="")
    bloqueado_em: Mapped[datetime | None] = mapped_column(nullable=True)
    plano: Mapped[str] = mapped_column(String(20), default="mensal", server_default="mensal")
    licenca_expira_em: Mapped[datetime | None] = mapped_column(nullable=True)
    # Cobrança: preços por ciclo, em centavos.
    valor_mensal_centavos: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    valor_anual_centavos: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Cancelamento (churn): data e motivo da saída da plataforma.
    cancelado_em: Mapped[datetime | None] = mapped_column(nullable=True)
    motivo_cancelamento: Mapped[str] = mapped_column(Text, default="", server_default="")


class ConversaORM(Base):
    __tablename__ = "conversas"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    contato: Mapped[str] = mapped_column(String(50), index=True)
    criado_em: Mapped[datetime] = mapped_column()

    mensagens: Mapped[list["MensagemORM"]] = relationship(
        back_populates="conversa", cascade="all, delete-orphan", order_by="MensagemORM.criado_em"
    )

    __table_args__ = (UniqueConstraint("tenant_id", "contato", name="uq_conversa_tenant_contato"),)


class MensagemORM(Base):
    __tablename__ = "mensagens"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    conversa_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("conversas.id"), index=True
    )
    autor: Mapped[str] = mapped_column(String(20))
    texto: Mapped[str] = mapped_column(Text)
    fontes: Mapped[str] = mapped_column(Text, default="")  # separadas por "|"
    criado_em: Mapped[datetime] = mapped_column()

    conversa: Mapped[ConversaORM] = relationship(back_populates="mensagens")


class FonteConhecimentoORM(Base):
    """Documento enviado pela escola, fragmentado em trechos de ``conhecimento``."""

    __tablename__ = "fontes_conhecimento"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    nome: Mapped[str] = mapped_column(String(300))
    tipo: Mapped[str] = mapped_column(String(30))
    total_trechos: Mapped[int] = mapped_column(Integer, default=0)
    criado_em: Mapped[datetime] = mapped_column()


class ConhecimentoORM(Base):
    __tablename__ = "conhecimento"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    # Documento de origem (quando o trecho veio de um upload da escola).
    fonte_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("fontes_conhecimento.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    tipo: Mapped[str] = mapped_column(String(30))
    titulo: Mapped[str] = mapped_column(String(300))
    conteudo: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(_DIM))
    criado_em: Mapped[datetime] = mapped_column()


class DocumentoORM(Base):
    __tablename__ = "documentos"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    nome: Mapped[str] = mapped_column(String(300))
    categoria: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(Text)


class TemplateORM(Base):
    __tablename__ = "templates"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    nome: Mapped[str] = mapped_column(String(200))
    categoria: Mapped[str] = mapped_column(String(30))
    idioma: Mapped[str] = mapped_column(String(10))
    corpo: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    # Id do template aprovado no provedor (Twilio Content API: HX...); vazio = texto livre.
    content_sid: Mapped[str] = mapped_column(
        String(64), default="", server_default=""
    )


class BroadcastORM(Base):
    __tablename__ = "broadcasts"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("templates.id"))
    titulo: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(30))
    agendado_para: Mapped[datetime | None] = mapped_column(nullable=True)
    criado_em: Mapped[datetime] = mapped_column()

    destinatarios: Mapped[list["DestinatarioORM"]] = relationship(
        back_populates="broadcast", cascade="all, delete-orphan"
    )


class DestinatarioORM(Base):
    __tablename__ = "destinatarios_broadcast"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    broadcast_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("broadcasts.id"), index=True
    )
    contato: Mapped[str] = mapped_column(String(50))
    parametros: Mapped[str] = mapped_column(Text, default="")  # separados por "|"
    status: Mapped[str] = mapped_column(String(20))
    # Id externo da mensagem na Meta (``wamid``), para casar eventos de status do webhook.
    mensagem_id_externo: Mapped[str] = mapped_column(String(128), default="", index=True)
    # Última atualização de status (envio ou webhook).
    atualizado_em: Mapped[datetime | None] = mapped_column(nullable=True)

    broadcast: Mapped[BroadcastORM] = relationship(back_populates="destinatarios")


class QuotaORM(Base):
    __tablename__ = "message_quotas"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    dia: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    limite_diario: Mapped[int] = mapped_column(Integer)
    enviados: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("tenant_id", "dia", name="uq_quota_tenant_dia"),)


# --------------------------------------------------------------------------- #
# Administração e grupos
# --------------------------------------------------------------------------- #
class UsuarioORM(Base):
    __tablename__ = "usuarios"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(Text)
    papel: Mapped[str] = mapped_column(String(20))
    # NULL para super admin (cross-tenant).
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column()


# Associação N:N entre grupos e contatos.
grupo_contatos = Table(
    "grupo_contatos",
    Base.metadata,
    Column("grupo_id", PGUUID(as_uuid=True), ForeignKey("grupos.id"), primary_key=True),
    Column("contato_id", PGUUID(as_uuid=True), ForeignKey("contatos.id"), primary_key=True),
)


# Associação N:N entre alunos e contatos (responsáveis).
aluno_responsaveis = Table(
    "aluno_responsaveis",
    Base.metadata,
    Column(
        "aluno_id",
        PGUUID(as_uuid=True),
        ForeignKey("alunos.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "contato_id",
        PGUUID(as_uuid=True),
        ForeignKey("contatos.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


# Associação N:N entre salas (turmas) e contatos (pais/responsáveis).
sala_contatos = Table(
    "sala_contatos",
    Base.metadata,
    Column(
        "sala_id",
        PGUUID(as_uuid=True),
        ForeignKey("salas.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "contato_id",
        PGUUID(as_uuid=True),
        ForeignKey("contatos.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class ContatoORM(Base):
    __tablename__ = "contatos"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    nome: Mapped[str] = mapped_column(String(200))
    telefone: Mapped[str] = mapped_column(String(50))
    # Responsável inativo (todos os seus alunos já são ex-alunos, §F1). Mantido no cadastro.
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    criado_em: Mapped[datetime] = mapped_column()

    grupos: Mapped[list["GrupoORM"]] = relationship(
        secondary=grupo_contatos, back_populates="membros"
    )
    salas: Mapped[list["SalaORM"]] = relationship(
        secondary=sala_contatos, back_populates="pais"
    )
    alunos: Mapped[list["AlunoORM"]] = relationship(
        secondary=aluno_responsaveis, back_populates="responsaveis"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "telefone", name="uq_contato_tenant_telefone"),
    )


class GrupoORM(Base):
    __tablename__ = "grupos"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    nome: Mapped[str] = mapped_column(String(200))
    descricao: Mapped[str] = mapped_column(Text, default="")
    criado_em: Mapped[datetime] = mapped_column()

    membros: Mapped[list[ContatoORM]] = relationship(
        secondary=grupo_contatos, back_populates="grupos"
    )

    __table_args__ = (UniqueConstraint("tenant_id", "nome", name="uq_grupo_tenant_nome"),)


class ProfessorORM(Base):
    __tablename__ = "professores"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    nome: Mapped[str] = mapped_column(String(200))
    telefone: Mapped[str] = mapped_column(String(50))
    # Senha (hash PBKDF2) para o login do professor no mural (§A1); vazio = sem acesso.
    senha_hash: Mapped[str] = mapped_column(Text, default="", server_default="")
    criado_em: Mapped[datetime] = mapped_column()

    __table_args__ = (
        UniqueConstraint("tenant_id", "telefone", name="uq_professor_tenant_telefone"),
    )


class SolicitacaoImpressaoORM(Base):
    __tablename__ = "solicitacoes_impressao"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    # Professor solicitante; ON DELETE SET NULL preserva o histórico da fila.
    professor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    professor_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    arquivo_nome: Mapped[str] = mapped_column(String(300))
    arquivo_url: Mapped[str] = mapped_column(Text, default="", server_default="")
    copias: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    colorido: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    frente_verso: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    observacao: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(
        String(20), default="pendente", server_default="pendente", index=True
    )
    criado_em: Mapped[datetime] = mapped_column()
    atualizado_em: Mapped[datetime] = mapped_column()


class SalaORM(Base):
    __tablename__ = "salas"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    nome: Mapped[str] = mapped_column(String(200))
    descricao: Mapped[str] = mapped_column(Text, default="")
    # Professor responsável pela série (1:1; um professor pode ter várias séries).
    # ON DELETE SET NULL: remover o professor apenas desvincula as séries.
    professor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    criado_em: Mapped[datetime] = mapped_column()

    pais: Mapped[list[ContatoORM]] = relationship(
        secondary=sala_contatos, back_populates="salas"
    )
    professor: Mapped["ProfessorORM | None"] = relationship()

    __table_args__ = (UniqueConstraint("tenant_id", "nome", name="uq_sala_tenant_nome"),)


class AlunoORM(Base):
    __tablename__ = "alunos"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    nome: Mapped[str] = mapped_column(String(200))
    matricula: Mapped[str] = mapped_column(String(50), default="")
    # Série/turma do aluno (1:1, obrigatória). A exclusão de uma série é mediada pelos
    # casos de uso (excluir os alunos ou movê-los), por isso a FK é restritiva.
    sala_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("salas.id"), nullable=False, index=True
    )
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column()

    sala: Mapped["SalaORM | None"] = relationship()
    responsaveis: Mapped[list[ContatoORM]] = relationship(
        secondary=aluno_responsaveis, back_populates="alunos"
    )


# --------------------------------------------------------------------------- #
# Mural do professor: recados + confirmação de leitura (§A1)
# --------------------------------------------------------------------------- #
class RecadoORM(Base):
    __tablename__ = "recados"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    titulo: Mapped[str] = mapped_column(String(300))
    corpo: Mapped[str] = mapped_column(Text)
    autor_id: Mapped[str] = mapped_column(String(64), default="", server_default="")
    autor_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    criado_em: Mapped[datetime] = mapped_column(index=True)

    leituras: Mapped[list["LeituraRecadoORM"]] = relationship(
        back_populates="recado", cascade="all, delete-orphan"
    )


class LeituraRecadoORM(Base):
    __tablename__ = "leituras_recado"

    recado_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("recados.id", ondelete="CASCADE"),
        primary_key=True,
    )
    professor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professores.id", ondelete="CASCADE"),
        primary_key=True,
    )
    lido_em: Mapped[datetime] = mapped_column()

    recado: Mapped[RecadoORM] = relationship(back_populates="leituras")


# --------------------------------------------------------------------------- #
# Auditoria de ações (usuários logados + LLM)
# --------------------------------------------------------------------------- #
class AuditoriaORM(Base):
    __tablename__ = "auditoria"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    # NULL para ações cross-tenant do super admin; index para a consulta por escola.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )
    ator: Mapped[str] = mapped_column(String(20))  # "usuario" | "llm" | "sistema"
    ator_id: Mapped[str] = mapped_column(String(128), default="")
    ator_nome: Mapped[str] = mapped_column(String(200), default="")
    acao: Mapped[str] = mapped_column(String(80), index=True)
    descricao: Mapped[str] = mapped_column(Text, default="")
    metadados: Mapped[dict] = mapped_column(JSON, default=dict)
    criado_em: Mapped[datetime] = mapped_column(index=True)


# --------------------------------------------------------------------------- #
# Respostas rápidas ("atalhos") da escola — ingeridas no RAG
# --------------------------------------------------------------------------- #
class RespostaRapidaORM(Base):
    __tablename__ = "respostas_rapidas"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    chave: Mapped[str] = mapped_column(String(200))
    conteudo: Mapped[str] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Documento de RAG gerado por esta resposta rápida; SET NULL ao remover a fonte.
    fonte_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("fontes_conhecimento.id", ondelete="SET NULL"),
        nullable=True,
    )
    criado_em: Mapped[datetime] = mapped_column()
    atualizado_em: Mapped[datetime] = mapped_column()

    __table_args__ = (
        UniqueConstraint("tenant_id", "chave", name="uq_resposta_rapida_tenant_chave"),
    )


# --------------------------------------------------------------------------- #
# Aviso geral temporizado (resposta automática do bot)
# --------------------------------------------------------------------------- #
class AvisoTemporizadoORM(Base):
    __tablename__ = "avisos_temporizados"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    mensagem: Mapped[str] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    inicia_em: Mapped[datetime | None] = mapped_column(nullable=True)
    expira_em: Mapped[datetime | None] = mapped_column(nullable=True)
    criado_em: Mapped[datetime] = mapped_column()
    atualizado_em: Mapped[datetime] = mapped_column()


# --------------------------------------------------------------------------- #
# Onda 2 · A2/A4 — Canal interno professor → secretaria (roteamento por assunto)
# --------------------------------------------------------------------------- #
class SolicitacaoInternaORM(Base):
    __tablename__ = "solicitacoes_internas"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    # Professor solicitante; ON DELETE SET NULL preserva o histórico do canal.
    professor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    professor_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    assunto: Mapped[str] = mapped_column(String(300))
    corpo: Mapped[str] = mapped_column(Text)
    categoria: Mapped[str] = mapped_column(
        String(20), default="secretaria", server_default="secretaria", index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="aberta", server_default="aberta", index=True
    )
    resposta: Mapped[str] = mapped_column(Text, default="", server_default="")
    respondido_em: Mapped[datetime | None] = mapped_column(nullable=True)
    criado_em: Mapped[datetime] = mapped_column()
    atualizado_em: Mapped[datetime] = mapped_column()


# --------------------------------------------------------------------------- #
# Onda 2 · A3 — Canal pai ↔ professor mediado (sem expor o número do professor)
# --------------------------------------------------------------------------- #
class MensagemMediadaORM(Base):
    __tablename__ = "mensagens_mediadas"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    professor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professores.id", ondelete="CASCADE"),
        index=True,
    )
    contato_telefone: Mapped[str] = mapped_column(String(50), index=True)
    contato_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    professor_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    direcao: Mapped[str] = mapped_column(String(30))
    corpo: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(index=True)


# --------------------------------------------------------------------------- #
# Onda 2 · B2 — Cota de impressão por professor
# --------------------------------------------------------------------------- #
class CotaImpressaoORM(Base):
    __tablename__ = "cotas_impressao"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    professor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professores.id", ondelete="CASCADE"),
        index=True,
    )
    limite_mensal: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    criado_em: Mapped[datetime] = mapped_column()
    atualizado_em: Mapped[datetime] = mapped_column()

    __table_args__ = (
        UniqueConstraint("tenant_id", "professor_id", name="uq_cota_impressao_tenant_professor"),
    )


# --------------------------------------------------------------------------- #
# System prompt personalizado por tenant (o "CLAUDE.md" da escola)
# --------------------------------------------------------------------------- #
class PromptTenantORM(Base):
    __tablename__ = "prompts_tenant"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), unique=True, index=True
    )
    conteudo: Mapped[str] = mapped_column(Text, default="")
    atualizado_em: Mapped[datetime] = mapped_column()


# --------------------------------------------------------------------------- #
# Onda 3 · I1 — Aviso de falta de professor e chamada de eventual
# --------------------------------------------------------------------------- #
class AvisoFaltaORM(Base):
    __tablename__ = "avisos_falta"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    # Professor ausente; ON DELETE SET NULL preserva o histórico de faltas.
    professor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    professor_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    data: Mapped[str] = mapped_column(String(10))  # "YYYY-MM-DD"
    motivo: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(
        String(20), default="aberta", server_default="aberta", index=True
    )
    eventual_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    eventual_telefone: Mapped[str] = mapped_column(String(50), default="", server_default="")
    eventuais_chamados: Mapped[list] = mapped_column(JSON, default=list)
    criado_em: Mapped[datetime] = mapped_column(index=True)
    atualizado_em: Mapped[datetime] = mapped_column()


# --------------------------------------------------------------------------- #
# Onda 3 · D1/D2/D3 — Ficha de matrícula digital (1:1 com o aluno)
# --------------------------------------------------------------------------- #
class FichaMatriculaORM(Base):
    __tablename__ = "fichas_matricula"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    # Ficha 1:1 com o aluno; apaga junto com o aluno.
    aluno_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("alunos.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    # Todos os campos da ficha (frente, verso e sensíveis) serializados em JSON.
    conteudo: Mapped[dict] = mapped_column(JSON, default=dict)
    criado_em: Mapped[datetime] = mapped_column()
    atualizado_em: Mapped[datetime] = mapped_column()


# --------------------------------------------------------------------------- #
# Onda 3 · E1 — Matrícula self-service iniciada pelo responsável (WhatsApp)
# --------------------------------------------------------------------------- #
class SolicitacaoMatriculaORM(Base):
    __tablename__ = "solicitacoes_matricula"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    contato_telefone: Mapped[str] = mapped_column(String(50), index=True)
    nome_responsavel: Mapped[str] = mapped_column(String(200), default="", server_default="")
    nome_aluno: Mapped[str] = mapped_column(String(200), default="", server_default="")
    status: Mapped[str] = mapped_column(
        String(30), default="iniciada", server_default="iniciada", index=True
    )
    observacao: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Lista de documentos anexados (nome/url/recebido_em) serializada em JSON.
    documentos: Mapped[list] = mapped_column(JSON, default=list)
    criado_em: Mapped[datetime] = mapped_column(index=True)
    atualizado_em: Mapped[datetime] = mapped_column()
