"""Ficha financeira/histórico da escola: preços por ciclo e cancelamento (churn).

Revision ID: 0007_ficha_financeira_tenant
Revises: 0007_auditoria
Create Date: 2026-06-19
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_ficha_financeira_tenant"
down_revision: str | None = "0007_auditoria"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("valor_mensal_centavos", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tenants",
        sa.Column("valor_anual_centavos", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tenants",
        sa.Column("cancelado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("motivo_cancelamento", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    for coluna in (
        "motivo_cancelamento",
        "cancelado_em",
        "valor_anual_centavos",
        "valor_mensal_centavos",
    ):
        op.drop_column("tenants", coluna)
