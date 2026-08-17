"""Tentativas por destinatário, para separar "não deu certo agora" de "não vai dar".

Até aqui, qualquer exceção no envio marcava o destinatário como FALHOU e o assunto morria
ali. Isso trata igual duas coisas opostas: um timeout de dez segundos e um template que não
existe na conta da escola. No primeiro caso o aviso se perde por nada — e a escola acredita
tê-lo mandado; no segundo, repetir só gasta cota e queima a qualidade do número.

Com o contador, a falha transitória volta para PENDENTE e a passada seguinte tenta de novo,
até o teto. O teto é obrigatório: sem ele, um número que dá timeout para sempre voltaria à
fila em toda passada, pelos 7 dias da janela de validade, tomando a vaga de quem ainda podia
receber.

Revision ID: 0045_dest_tentativas
Revises: 0044_envios_iniciados
Create Date: 2026-08-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0045_dest_tentativas"
down_revision = "0044_envios_iniciados"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "destinatarios_broadcast",
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("destinatarios_broadcast", "tentativas")
