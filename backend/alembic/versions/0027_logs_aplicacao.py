"""Cria logs_aplicacao — log operacional consultável no painel (§16).

Item 8 do checklist de pré-deploy: existia auditoria de negócio e loggers por módulo, mas
nenhum logging estruturado e nenhum lugar onde olhar. Uma falha em produção só aparecia
se alguém abrisse os logs do Render no momento certo — e o log do Render é volátil.

Sem FK para ``tenants``: um log pode nascer antes de sabermos a escola (falha de
roteamento do inbound, erro de autenticação) ou sobreviver à remoção dela, e uma FK faria
a exclusão de escola falhar por causa de uma linha de log.

Revision ID: 0027_logs_aplicacao
Revises: 0026_inbound_atendimento
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0027_logs_aplicacao"
down_revision: str | None = "0026_inbound_atendimento"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "logs_aplicacao",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("nivel", sa.String(10), nullable=False),
        sa.Column("logger", sa.String(120), nullable=False, server_default=""),
        sa.Column("mensagem", sa.Text(), nullable=False, server_default=""),
        sa.Column("correlacao_id", sa.String(40), nullable=False, server_default=""),
        sa.Column("rota", sa.String(200), nullable=False, server_default=""),
        sa.Column("metodo", sa.String(10), nullable=False, server_default=""),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("duracao_ms", sa.Integer(), nullable=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), nullable=True),
        sa.Column("excecao", sa.Text(), nullable=False, server_default=""),
        sa.Column("metadados", JSON(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_logs_aplicacao_criado_em", "logs_aplicacao", ["criado_em"])
    op.create_index("ix_logs_aplicacao_nivel", "logs_aplicacao", ["nivel"])
    op.create_index("ix_logs_aplicacao_logger", "logs_aplicacao", ["logger"])
    op.create_index("ix_logs_aplicacao_correlacao_id", "logs_aplicacao", ["correlacao_id"])
    op.create_index("ix_logs_aplicacao_tenant_id", "logs_aplicacao", ["tenant_id"])
    # A listagem do painel é sempre "nível X, mais recentes primeiro".
    op.create_index(
        "ix_logs_aplicacao_nivel_criado_em", "logs_aplicacao", ["nivel", "criado_em"]
    )


def downgrade() -> None:
    op.drop_index("ix_logs_aplicacao_nivel_criado_em", table_name="logs_aplicacao")
    op.drop_index("ix_logs_aplicacao_tenant_id", table_name="logs_aplicacao")
    op.drop_index("ix_logs_aplicacao_correlacao_id", table_name="logs_aplicacao")
    op.drop_index("ix_logs_aplicacao_logger", table_name="logs_aplicacao")
    op.drop_index("ix_logs_aplicacao_nivel", table_name="logs_aplicacao")
    op.drop_index("ix_logs_aplicacao_criado_em", table_name="logs_aplicacao")
    op.drop_table("logs_aplicacao")
