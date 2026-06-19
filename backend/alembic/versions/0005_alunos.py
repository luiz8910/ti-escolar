"""Alunos e vínculo N:N com responsáveis (contatos); série 1:1 com salas.

Revision ID: 0005_alunos
Revises: 0004_conhecimento_prompt
Create Date: 2026-06-18
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0005_alunos"
down_revision: str | None = "0004_conhecimento_prompt"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alunos",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("matricula", sa.String(50), nullable=False, server_default=""),
        sa.Column(
            "sala_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("salas.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "aluno_responsaveis",
        sa.Column(
            "aluno_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("alunos.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "contato_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("contatos.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    for tabela in ("aluno_responsaveis", "alunos"):
        op.drop_table(tabela)
