"""Base de conhecimento enviada pela escola (fontes + fonte_id em conhecimento) e
system prompt personalizado por tenant.

Revision ID: 0004_conhecimento_prompt
Revises: 0003_salas
Create Date: 2026-06-15
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0004_conhecimento_prompt"
down_revision: str | None = "0003_salas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fontes_conhecimento",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column("nome", sa.String(300), nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("total_trechos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )

    op.add_column(
        "conhecimento",
        sa.Column(
            "fonte_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("fontes_conhecimento.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_conhecimento_fonte_id", "conhecimento", ["fonte_id"]
    )

    op.create_table(
        "prompts_tenant",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("conteudo", sa.Text(), nullable=False, server_default=""),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("prompts_tenant")
    op.drop_index("ix_conhecimento_fonte_id", table_name="conhecimento")
    op.drop_column("conhecimento", "fonte_id")
    op.drop_table("fontes_conhecimento")
