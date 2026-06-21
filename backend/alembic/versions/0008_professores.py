"""Professores (nome + telefone) e vínculo 1:1 com séries via salas.professor_id.

Revision ID: 0008_professores
Revises: 0007_ficha_financeira_tenant
Create Date: 2026-06-21
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0008_professores"
down_revision: str | None = "0007_ficha_financeira_tenant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "professores",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("telefone", sa.String(50), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "telefone", name="uq_professor_tenant_telefone"),
    )

    # Professor responsável pela série (1:1); ON DELETE SET NULL desvincula ao remover.
    op.add_column(
        "salas",
        sa.Column(
            "professor_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("professores.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_salas_professor_id", "salas", ["professor_id"])


def downgrade() -> None:
    op.drop_index("ix_salas_professor_id", table_name="salas")
    op.drop_column("salas", "professor_id")
    op.drop_table("professores")
