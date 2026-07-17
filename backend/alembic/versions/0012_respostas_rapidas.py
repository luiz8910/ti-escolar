"""Respostas rápidas ("atalhos") por tenant, ingeridas no RAG.

Revision ID: 0012_respostas_rapidas
Revises: 0011_tenant_telefone_contato
Create Date: 2026-07-17
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0012_respostas_rapidas"
down_revision: str | None = "0011_tenant_telefone_contato"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "respostas_rapidas",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column("chave", sa.String(200), nullable=False),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "fonte_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("fontes_conhecimento.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "chave", name="uq_resposta_rapida_tenant_chave"),
    )


def downgrade() -> None:
    op.drop_table("respostas_rapidas")
