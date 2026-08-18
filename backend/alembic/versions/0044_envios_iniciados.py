"""Livro de conversas iniciadas, no lugar do contador por dia de calendário.

A cota da Meta é de **clientes únicos numa janela de 24h corridas**, medida no **portfólio**
(Meta Business Account) desde out/2025 — não por data e não por escola. O contador antigo
(`message_quotas`, uma linha por tenant/dia em UTC) não conseguia responder à pergunta que
importa, porque um agregado perde o instante de cada envio: sem instante não há janela
corrida nem como dizer quando a capacidade volta. E, contando por escola, cinco escolas de
teste acreditariam ter 1250 de capacidade para a Graph API recusar na 251ª.

`envios_iniciados` guarda uma linha por envio, com o contato — que é o que permite contar
**distintos**, já que o mesmo responsável em dois avisos da mesma janela é uma conversa só.

A tabela antiga é removida em vez de mantida: o dado dela não é convertível (não há hora do
envio para reconstruir), e deixá-la viva convidaria alguém a lê-la achando que vale.

Revision ID: 0044_envios_iniciados
Revises: 0043_destinatario_erro
Create Date: 2026-08-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "0044_envios_iniciados"
down_revision = "0043_destinatario_erro"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "envios_iniciados",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "meta_business_id", sa.String(64), nullable=False, server_default=""
        ),
        sa.Column("contato", sa.String(50), nullable=False),
        sa.Column("enviado_em", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_envios_iniciados_tenant_id", "envios_iniciados", ["tenant_id"])
    op.create_index(
        "ix_envios_iniciados_janela",
        "envios_iniciados",
        ["meta_business_id", "enviado_em"],
    )
    op.drop_table("message_quotas")


def downgrade() -> None:
    op.create_table(
        "message_quotas",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("dia", sa.String(10), nullable=False),
        sa.Column("limite_diario", sa.Integer(), nullable=False),
        sa.Column("enviados", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("tenant_id", "dia", name="uq_quota_tenant_dia"),
    )
    op.create_index("ix_message_quotas_tenant_id", "message_quotas", ["tenant_id"])
    op.drop_index("ix_envios_iniciados_janela", table_name="envios_iniciados")
    op.drop_index("ix_envios_iniciados_tenant_id", table_name="envios_iniciados")
    op.drop_table("envios_iniciados")
