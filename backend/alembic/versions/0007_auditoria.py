"""Log de auditoria de ações (usuários logados no admin e ações da LLM).

Revision ID: 0007_auditoria
Revises: 0006_destinatario_entrega
Create Date: 2026-06-19
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0007_auditoria"
down_revision: str | None = "0006_destinatario_entrega"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auditoria",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=True,
        ),
        sa.Column("ator", sa.String(20), nullable=False),
        sa.Column("ator_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("ator_nome", sa.String(200), nullable=False, server_default=""),
        sa.Column("acao", sa.String(80), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False, server_default=""),
        sa.Column("metadados", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auditoria_tenant_id", "auditoria", ["tenant_id"])
    op.create_index("ix_auditoria_acao", "auditoria", ["acao"])
    op.create_index("ix_auditoria_criado_em", "auditoria", ["criado_em"])


def downgrade() -> None:
    op.drop_index("ix_auditoria_criado_em", table_name="auditoria")
    op.drop_index("ix_auditoria_acao", table_name="auditoria")
    op.drop_index("ix_auditoria_tenant_id", table_name="auditoria")
    op.drop_table("auditoria")
