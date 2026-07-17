"""Cota (franquia mensal) de impressão por professor (§B2).

Revision ID: 0018_cota_impressao
Revises: 0017_mensagens_mediadas
Create Date: 2026-07-17
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0018_cota_impressao"
down_revision: str | None = "0017_mensagens_mediadas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cotas_impressao",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column(
            "professor_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("professores.id", ondelete="CASCADE"),
            index=True,
        ),
        sa.Column("limite_mensal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "professor_id", name="uq_cota_impressao_tenant_professor"
        ),
    )


def downgrade() -> None:
    op.drop_table("cotas_impressao")
