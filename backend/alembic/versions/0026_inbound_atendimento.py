"""Cria inbound_atendimento — idempotência durável do inbound (§9e.1).

Substitui o cache de processo (``CacheIdempotenciaMemoria``), que resolvia só a reentrega
que caísse **na mesma réplica e antes do próximo restart**. Com mais de uma instância no
Render, a reentrega da Meta chega tipicamente em outra réplica, onde o cache de memória
não sabe de nada — e o mesmo recado é atendido, respondido e cobrado na LLM duas vezes.

Guarda estado, não um booleano: ``em_atendimento`` (alguém está respondendo agora) é
diferente de ``concluida`` (a dúvida já foi sanada). A reentrega chega justamente durante
a primeira, enquanto ela espera a LLM.

Revision ID: 0026_inbound_atendimento
Revises: 0025_controle_taxa
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0026_inbound_atendimento"
down_revision: str | None = "0025_controle_taxa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inbound_atendimento",
        sa.Column("chave", sa.String(200), primary_key=True),
        sa.Column(
            "tenant_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=True,
        ),
        sa.Column("origem", sa.String(50), nullable=False, server_default=""),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="em_atendimento"
        ),
        sa.Column("resumo", sa.Text(), nullable=False, server_default=""),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_inbound_atendimento_tenant_id", "inbound_atendimento", ["tenant_id"])
    op.create_index("ix_inbound_atendimento_status", "inbound_atendimento", ["status"])
    op.create_index("ix_inbound_atendimento_criado_em", "inbound_atendimento", ["criado_em"])


def downgrade() -> None:
    op.drop_index("ix_inbound_atendimento_criado_em", table_name="inbound_atendimento")
    op.drop_index("ix_inbound_atendimento_status", table_name="inbound_atendimento")
    op.drop_index("ix_inbound_atendimento_tenant_id", table_name="inbound_atendimento")
    op.drop_table("inbound_atendimento")
