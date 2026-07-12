"""ContentSid do template aprovado (Twilio Content API) em templates.content_sid.

Revision ID: 0010_template_content_sid
Revises: 0009_tenant_whatsapp
Create Date: 2026-07-12
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_template_content_sid"
down_revision: str | None = "0009_tenant_whatsapp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "templates",
        sa.Column("content_sid", sa.String(64), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("templates", "content_sid")
