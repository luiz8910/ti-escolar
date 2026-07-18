"""Aviso de falta de professor e chamada de eventual (§I1).

Revision ID: 0020_avisos_falta
Revises: 0019_contato_ativo
Create Date: 2026-07-17
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0020_avisos_falta"
down_revision: str | None = "0019_contato_ativo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "avisos_falta",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column(
            "professor_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("professores.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("professor_nome", sa.String(200), nullable=False, server_default=""),
        sa.Column("data", sa.String(10), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="aberta", index=True),
        sa.Column("eventual_nome", sa.String(200), nullable=False, server_default=""),
        sa.Column("eventual_telefone", sa.String(50), nullable=False, server_default=""),
        sa.Column("eventuais_chamados", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_avisos_falta_criado_em", "avisos_falta", ["criado_em"])


def downgrade() -> None:
    op.drop_index("ix_avisos_falta_criado_em", table_name="avisos_falta")
    op.drop_table("avisos_falta")
