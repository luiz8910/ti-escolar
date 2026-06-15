"""Schema inicial: extensão pgvector + tabelas.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-14
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op
from app.config import get_settings

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DIM = get_settings().embedding_dim


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "tenants",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "conversas",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column("contato", sa.String(50), index=True, nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "contato", name="uq_conversa_tenant_contato"),
    )

    op.create_table(
        "mensagens",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("conversa_id", PGUUID(as_uuid=True), sa.ForeignKey("conversas.id"), index=True),
        sa.Column("autor", sa.String(20), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("fontes", sa.Text(), nullable=False, server_default=""),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "conhecimento",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("titulo", sa.String(300), nullable=False),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(_DIM), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "documentos",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column("nome", sa.String(300), nullable=False),
        sa.Column("categoria", sa.String(100), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
    )

    op.create_table(
        "templates",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("categoria", sa.String(30), nullable=False),
        sa.Column("idioma", sa.String(10), nullable=False),
        sa.Column("corpo", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
    )

    op.create_table(
        "broadcasts",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column("template_id", PGUUID(as_uuid=True), sa.ForeignKey("templates.id")),
        sa.Column("titulo", sa.String(300), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("agendado_para", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "destinatarios_broadcast",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("broadcast_id", PGUUID(as_uuid=True), sa.ForeignKey("broadcasts.id"), index=True),
        sa.Column("contato", sa.String(50), nullable=False),
        sa.Column("parametros", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False),
    )

    op.create_table(
        "message_quotas",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column("dia", sa.String(10), nullable=False),
        sa.Column("limite_diario", sa.Integer(), nullable=False),
        sa.Column("enviados", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("tenant_id", "dia", name="uq_quota_tenant_dia"),
    )


def downgrade() -> None:
    for tabela in (
        "message_quotas",
        "destinatarios_broadcast",
        "broadcasts",
        "templates",
        "documentos",
        "conhecimento",
        "mensagens",
        "conversas",
        "tenants",
    ):
        op.drop_table(tabela)
