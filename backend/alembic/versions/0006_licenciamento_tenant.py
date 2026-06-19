"""Licenciamento/cobrança/bloqueio da escola (tenant): status, plano e expiração.

Revision ID: 0006_licenciamento_tenant
Revises: 0005_alunos
Create Date: 2026-06-19
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_licenciamento_tenant"
down_revision: str | None = "0005_alunos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("status", sa.String(20), nullable=False, server_default="ativo"),
    )
    op.add_column(
        "tenants",
        sa.Column("motivo_bloqueio", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "tenants",
        sa.Column("bloqueado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("plano", sa.String(20), nullable=False, server_default="mensal"),
    )
    op.add_column(
        "tenants",
        sa.Column("licenca_expira_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    for coluna in (
        "licenca_expira_em",
        "plano",
        "bloqueado_em",
        "motivo_bloqueio",
        "status",
    ):
        op.drop_column("tenants", coluna)
