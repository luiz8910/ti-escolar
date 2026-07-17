"""Canal pai ↔ professor mediado, sem expor o número do professor (§A3).

Revision ID: 0017_mensagens_mediadas
Revises: 0016_solicitacoes_internas
Create Date: 2026-07-17
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0017_mensagens_mediadas"
down_revision: str | None = "0016_solicitacoes_internas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mensagens_mediadas",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column(
            "professor_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("professores.id", ondelete="CASCADE"),
            index=True,
        ),
        sa.Column("contato_telefone", sa.String(50), nullable=False, index=True),
        sa.Column("contato_nome", sa.String(200), nullable=False, server_default=""),
        sa.Column("professor_nome", sa.String(200), nullable=False, server_default=""),
        sa.Column("direcao", sa.String(30), nullable=False),
        sa.Column("corpo", sa.Text(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mensagens_mediadas_criado_em", "mensagens_mediadas", ["criado_em"])


def downgrade() -> None:
    op.drop_index("ix_mensagens_mediadas_criado_em", table_name="mensagens_mediadas")
    op.drop_table("mensagens_mediadas")
