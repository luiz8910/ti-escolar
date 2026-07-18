"""Ficha de matrícula digital por aluno (§D1/D2/D3).

Revision ID: 0021_ficha_matricula
Revises: 0020_avisos_falta
Create Date: 2026-07-17
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0021_ficha_matricula"
down_revision: str | None = "0020_avisos_falta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fichas_matricula",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column(
            "aluno_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("alunos.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("conteudo", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("fichas_matricula")
