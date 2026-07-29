"""Cria controle_taxa — contador de janela fixa do rate limiting de entrada.

Item 5 do checklist de pré-deploy (§15): não havia limite de taxa em lugar nenhum, o que
deixava o ``POST /api/admin/login`` aberto a brute force e o webhook inbound aberto a um
número em loop consumindo a cota de LLM da escola.

A tabela é intencionalmente **sem FK e sem tenant_id**: a chave pode ser um IP ou um
telefone que ainda não pertence a nenhuma escola — justamente o caso do atacante.

Revision ID: 0025_controle_taxa
Revises: 0024_tenant_meta_phone_number_id
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_controle_taxa"
down_revision: str | None = "0024_tenant_meta_phone_number_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "controle_taxa",
        sa.Column("chave", sa.String(200), primary_key=True),
        sa.Column("janela_inicio", sa.DateTime(), nullable=False),
        sa.Column("contador", sa.Integer(), nullable=False, server_default="0"),
    )
    # Usado pela limpeza periódica das janelas já vencidas.
    op.create_index("ix_controle_taxa_janela_inicio", "controle_taxa", ["janela_inicio"])


def downgrade() -> None:
    op.drop_index("ix_controle_taxa_janela_inicio", table_name="controle_taxa")
    op.drop_table("controle_taxa")
