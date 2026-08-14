"""Motivo da falha por destinatário do broadcast.

O primeiro disparo real do produto falhou nos dois destinatários e o painel mostrou apenas
"Falhou". Não havia mais nada em lugar nenhum: `EnviarBroadcast` capturava a exceção para
não derrubar o lote — o que é certo — e a descartava junto, o que não é. A causa (o
template não existia na conta da escola) só apareceu depois de consultar a Graph API à mão.

Guardar o motivo é o que transforma a tela de disparos em algo diagnosticável: "Falhou"
vira "Falhou — template name does not exist in the translation".

Revision ID: 0043_destinatario_erro
Revises: 0042_wabas_multiplas
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043_destinatario_erro"
down_revision = "0042_wabas_multiplas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "destinatarios_broadcast",
        sa.Column("erro", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("destinatarios_broadcast", "erro")
