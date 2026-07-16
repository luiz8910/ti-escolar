"""Telefone de contato público por escola (tenants.telefone_contato), informativo.

Revision ID: 0011_tenant_telefone_contato
Revises: 0010_template_content_sid
Create Date: 2026-07-15
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_tenant_telefone_contato"
down_revision: str | None = "0010_template_content_sid"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "telefone_contato",
            sa.String(30),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "telefone_contato")
