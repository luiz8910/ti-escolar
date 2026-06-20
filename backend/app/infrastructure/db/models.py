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
    # Licenciamento / cobrança / bloqueio.
    status: Mapped[str] = mapped_column(String(20), default="ativo", server_default="ativo")
    motivo_bloqueio: Mapped[str] = mapped_column(Text, default="", server_default="")
    bloqueado_em: Mapped[datetime | None] = mapped_column(nullable=True)
    plano: Mapped[str] = mapped_column(String(20), default="mensal", server_default="mensal")
    licenca_expira_em: Mapped[datetime | None] = mapped_column(nullable=True)


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


class SalaORM(Base):
    __tablename__ = "salas"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    nome: Mapped[str] = mapped_column(String(200))
    descricao: Mapped[str] = mapped_column(Text, default="")
    criado_em: Mapped[datetime] = mapped_column()

    pais: Mapped[list[ContatoORM]] = relationship(
        secondary=sala_contatos, back_populates="salas"
    )

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
