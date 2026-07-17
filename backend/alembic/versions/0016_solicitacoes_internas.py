"""Canal interno professor → secretaria/gestão/pedagógico (§A2/A4).

Revision ID: 0016_solicitacoes_internas
Revises: 0015_mural_professor
Create Date: 2026-07-17
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0016_solicitacoes_internas"
down_revision: str | None = "0015_mural_professor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "solicitacoes_internas",
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
        sa.Column("assunto", sa.String(300), nullable=False),
        sa.Column("corpo", sa.Text(), nullable=False),
        sa.Column("categoria", sa.String(20), nullable=False, server_default="secretaria"),
        sa.Column("status", sa.String(20), nullable=False, server_default="aberta"),
        sa.Column("resposta", sa.Text(), nullable=False, server_default=""),
        sa.Column("respondido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_solicitacoes_internas_categoria", "solicitacoes_internas", ["categoria"]
    )
    op.create_index("ix_solicitacoes_internas_status", "solicitacoes_internas", ["status"])


def downgrade() -> None:
    op.drop_index("ix_solicitacoes_internas_status", table_name="solicitacoes_internas")
    op.drop_index("ix_solicitacoes_internas_categoria", table_name="solicitacoes_internas")
    op.drop_table("solicitacoes_internas")
