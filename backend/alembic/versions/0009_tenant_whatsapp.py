"""Número de WhatsApp por escola (tenants.whatsapp_numero) para roteamento multi-tenant.

Revision ID: 0009_tenant_whatsapp
Revises: 0008_professores
Create Date: 2026-07-11
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_tenant_whatsapp"
down_revision: str | None = "0008_professores"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "whatsapp_numero",
            sa.String(30),
            nullable=False,
            server_default="",
        ),
    )
    op.create_index("ix_tenants_whatsapp_numero", "tenants", ["whatsapp_numero"])


def downgrade() -> None:
    op.drop_index("ix_tenants_whatsapp_numero", table_name="tenants")
    op.drop_column("tenants", "whatsapp_numero")
