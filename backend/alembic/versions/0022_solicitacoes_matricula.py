"""Matrícula self-service iniciada pelo responsável via WhatsApp (§E1).

Revision ID: 0022_solicitacoes_matricula
Revises: 0021_ficha_matricula
Create Date: 2026-07-17
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0022_solicitacoes_matricula"
down_revision: str | None = "0021_ficha_matricula"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "solicitacoes_matricula",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column("contato_telefone", sa.String(50), nullable=False, index=True),
        sa.Column("nome_responsavel", sa.String(200), nullable=False, server_default=""),
        sa.Column("nome_aluno", sa.String(200), nullable=False, server_default=""),
        sa.Column("status", sa.String(30), nullable=False, server_default="iniciada", index=True),
        sa.Column("observacao", sa.Text(), nullable=False, server_default=""),
        sa.Column("documentos", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_solicitacoes_matricula_criado_em", "solicitacoes_matricula", ["criado_em"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_solicitacoes_matricula_criado_em", table_name="solicitacoes_matricula"
    )
    op.drop_table("solicitacoes_matricula")
