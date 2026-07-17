"""Responsável ativo/inativo — ciclo de vida do responsável na progressão de série (§F1).

Revision ID: 0019_contato_ativo
Revises: 0018_cota_impressao
Create Date: 2026-07-17
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_contato_ativo"
down_revision: str | None = "0018_cota_impressao"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contatos",
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("contatos", "ativo")
