"""Mural do professor: senha do professor + recados + confirmação de leitura (§A1).

Revision ID: 0015_mural_professor
Revises: 0014_solicitacoes_impressao
Create Date: 2026-07-17
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0015_mural_professor"
down_revision: str | None = "0014_solicitacoes_impressao"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Senha (hash) do professor para o login próprio do mural.
    op.add_column(
        "professores",
        sa.Column("senha_hash", sa.Text(), nullable=False, server_default=""),
    )

    op.create_table(
        "recados",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column("titulo", sa.String(300), nullable=False),
        sa.Column("corpo", sa.Text(), nullable=False),
        sa.Column("autor_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("autor_nome", sa.String(200), nullable=False, server_default=""),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_recados_criado_em", "recados", ["criado_em"])

    op.create_table(
        "leituras_recado",
        sa.Column(
            "recado_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("recados.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "professor_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("professores.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("lido_em", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("leituras_recado")
    op.drop_index("ix_recados_criado_em", table_name="recados")
    op.drop_table("recados")
    op.drop_column("professores", "senha_hash")
