"""Avisos temporizados por tenant (resposta automática do bot).

Revision ID: 0013_avisos_temporizados
Revises: 0012_respostas_rapidas
Create Date: 2026-07-17
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0013_avisos_temporizados"
down_revision: str | None = "0012_respostas_rapidas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "avisos_temporizados",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column("mensagem", sa.Text(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("inicia_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("avisos_temporizados")
