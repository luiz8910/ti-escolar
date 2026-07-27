"""Remove templates.content_sid — conceito exclusivo da Twilio (Content API).

Com a migração para a Meta Cloud API direta (§9e), o envio por template aprovado passa a ser
identificado por ``nome`` + ``idioma`` (que a entidade ``MessageTemplate`` já carrega), e o
``ContentSid`` (``HX...``) da Twilio deixa de existir no produto.

Revision ID: 0023_remover_content_sid
Revises: 0022_solicitacoes_matricula
Create Date: 2026-07-27
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_remover_content_sid"
down_revision: str | None = "0022_solicitacoes_matricula"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("templates", "content_sid")


def downgrade() -> None:
    # Recria a coluna vazia; os ContentSid antigos não são recuperáveis pelo downgrade.
    op.add_column(
        "templates",
        sa.Column("content_sid", sa.String(64), nullable=False, server_default=""),
    )
