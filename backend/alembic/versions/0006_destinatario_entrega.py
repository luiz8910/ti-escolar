"""Status de entrega por destinatário: id externo da Meta e timestamp (não-entrega reativa).

Revision ID: 0006_destinatario_entrega
Revises: 0006_licenciamento_tenant
Create Date: 2026-06-19
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_destinatario_entrega"
down_revision: str | None = "0006_licenciamento_tenant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "destinatarios_broadcast",
        sa.Column(
            "mensagem_id_externo",
            sa.String(128),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "destinatarios_broadcast",
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_destinatarios_broadcast_mensagem_id_externo",
        "destinatarios_broadcast",
        ["mensagem_id_externo"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_destinatarios_broadcast_mensagem_id_externo",
        table_name="destinatarios_broadcast",
    )
    op.drop_column("destinatarios_broadcast", "atualizado_em")
    op.drop_column("destinatarios_broadcast", "mensagem_id_externo")
