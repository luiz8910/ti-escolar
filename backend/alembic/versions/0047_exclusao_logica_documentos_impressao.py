"""Exclusão lógica de documentos recebidos e pedidos de impressão (``deleted_at``).

Excluir um documento ou tirar um pedido da fila de impressão passou a apagar **o arquivo** e
a **marcar a linha**, em vez de apagá-la. A linha marcada fica reduzida — sem ponteiro para o
storage — e some de toda leitura do painel, mas continua visível para a dedupe do webhook:
sem ela, a reentrega da mesma mídia pela Meta recriaria o documento ou o pedido que a escola
acabou de tirar.

Nos documentos, a linha marcada ganha o prazo curto do descarte e o expurgo a apaga de vez.
Na fila de impressão ainda não há expurgo — ela fica, sem arquivo.

Sem índice: toda consulta que filtra ``deleted_at`` já filtra ``tenant_id`` antes, e a
fração de linhas marcadas é pequena.

Revision ID: 0047_exclusao_logica
Revises: 0046_chave_impressao
Create Date: 2026-08-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047_exclusao_logica"
down_revision = "0046_chave_impressao"
branch_labels = None
depends_on = None

_TABELAS = ("documentos_recebidos", "solicitacoes_impressao")


def upgrade() -> None:
    for tabela in _TABELAS:
        op.add_column(
            tabela, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    # Descer a coluna devolve ao painel as linhas marcadas — já sem arquivo, com download
    # em 404. Apagá-las antes é o que o comportamento anterior faria.
    for tabela in _TABELAS:
        op.execute(sa.text(f"DELETE FROM {tabela} WHERE deleted_at IS NOT NULL"))
        op.drop_column(tabela, "deleted_at")
