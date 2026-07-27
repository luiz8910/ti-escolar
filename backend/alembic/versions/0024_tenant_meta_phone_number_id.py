"""Adiciona tenants.meta_phone_number_id — o id do número da escola na Meta (§9e.1).

É o identificador que a Graph API exige na URL de envio (``/{phone_number_id}/messages``) e
o que o webhook devolve em ``value.metadata.phone_number_id`` para rotear o inbound para a
escola certa. Coexiste com ``whatsapp_numero`` (o mesmo número em E.164 legível).

**Unicidade parcial:** duas escolas com o mesmo id tornariam o roteamento do inbound
ambíguo, então o índice é ``UNIQUE``. Mas o default é ``''`` (escola ainda sem número
registrado na Meta), e um UNIQUE simples só permitiria **uma** escola nesse estado — por
isso o índice é parcial (``WHERE meta_phone_number_id <> ''``).

Revision ID: 0024_tenant_meta_phone_number_id
Revises: 0023_remover_content_sid
Create Date: 2026-07-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024_tenant_meta_phone_number_id"
down_revision: str | None = "0023_remover_content_sid"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("meta_phone_number_id", sa.String(64), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_tenants_meta_phone_number_id",
        "tenants",
        ["meta_phone_number_id"],
        unique=True,
        postgresql_where=sa.text("meta_phone_number_id <> ''"),
    )


def downgrade() -> None:
    op.drop_index("ix_tenants_meta_phone_number_id", table_name="tenants")
    op.drop_column("tenants", "meta_phone_number_id")
