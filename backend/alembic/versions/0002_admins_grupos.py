"""Administração (usuários) e grupos de contatos.

Revision ID: 0002_admins_grupos
Revises: 0001_initial
Create Date: 2026-06-15
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0002_admins_grupos"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("senha_hash", sa.Text(), nullable=False),
        sa.Column("papel", sa.String(20), nullable=False),
        sa.Column(
            "tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True, index=True
        ),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "contatos",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("telefone", sa.String(50), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "telefone", name="uq_contato_tenant_telefone"),
    )

    op.create_table(
        "grupos",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), index=True),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False, server_default=""),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "nome", name="uq_grupo_tenant_nome"),
    )

    op.create_table(
        "grupo_contatos",
        sa.Column("grupo_id", PGUUID(as_uuid=True), sa.ForeignKey("grupos.id"), primary_key=True),
        sa.Column(
            "contato_id", PGUUID(as_uuid=True), sa.ForeignKey("contatos.id"), primary_key=True
        ),
    )


def downgrade() -> None:
    for tabela in ("grupo_contatos", "grupos", "contatos", "usuarios"):
        op.drop_table(tabela)
