"""Salas (turmas) e vínculo N:N com pais/responsáveis (contatos).

Revision ID: 0003_salas
Revises: 0002_admins_grupos
Create Date: 2026-06-15
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0003_salas"
down_revision: str | None = "0002_admins_grupos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "salas",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False, server_default=""),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "nome", name="uq_sala_tenant_nome"),
    )

    op.create_table(
        "sala_contatos",
        sa.Column(
            "sala_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("salas.id", ondelete="CASCADE"),
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
    for tabela in ("sala_contatos", "salas"):
        op.drop_table(tabela)
