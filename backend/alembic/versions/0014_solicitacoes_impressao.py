"""Fila de solicitações de impressão dos professores.

Revision ID: 0014_solicitacoes_impressao
Revises: 0013_avisos_temporizados
Create Date: 2026-07-17
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0014_solicitacoes_impressao"
down_revision: str | None = "0013_avisos_temporizados"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "solicitacoes_impressao",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column(
            "professor_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("professores.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("professor_nome", sa.String(200), nullable=False, server_default=""),
        sa.Column("arquivo_nome", sa.String(300), nullable=False),
        sa.Column("arquivo_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("copias", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("colorido", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("frente_verso", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("observacao", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="pendente"),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_solicitacoes_impressao_professor_id",
        "solicitacoes_impressao",
        ["professor_id"],
    )
    op.create_index(
        "ix_solicitacoes_impressao_status", "solicitacoes_impressao", ["status"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_solicitacoes_impressao_status", table_name="solicitacoes_impressao"
    )
    op.drop_index(
        "ix_solicitacoes_impressao_professor_id", table_name="solicitacoes_impressao"
    )
    op.drop_table("solicitacoes_impressao")
