"""Impressão pelo WhatsApp: professor ativo e arquivo guardado na fila.

Duas mudanças, uma feature só — o professor manda o arquivo para o número da escola e ele
cai na fila de impressão em vez de virar atendimento.

1. **``professores.ativo``.** Sem ela, "professor cadastrado" e "professor da escola" são a
   mesma coisa, e quem saiu continuaria com o número reconhecido pelo inbound — mandando
   material direto para a impressora da secretaria. Apagar o cadastro não serve de
   substituto: a fila de impressão e o relatório mensal dependem dele para o histórico.
   Nasce ``true`` para todo mundo: quem já está cadastrado hoje está trabalhando.

2. **Arquivo e origem na ``solicitacoes_impressao``.** Pelo portal, o arquivo é apenas
   referenciado (``arquivo_url``); pelo WhatsApp os bytes precisam ficar com a escola,
   senão o pedido chega à fila sem o que imprimir. ``chave_storage`` aponta para o
   ``ArquivoStorage`` (§6k) — o mesmo desenho dos documentos recebidos, com os bytes fora
   da tabela de negócio. ``media_id`` deduplica a reentrega do webhook, e ``origem``
   avisa a secretaria de que aquele número de cópias foi **palpite sobre a legenda**, não
   formulário preenchido.

Revision ID: 0038_impressao_whatsapp
Revises: 0037_conversa_sessao
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0038_impressao_whatsapp"
down_revision: str | None = "0037_conversa_sessao"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "professores",
        sa.Column(
            "ativo", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
    )
    op.create_index("ix_professores_ativo", "professores", ["ativo"])

    op.add_column(
        "solicitacoes_impressao",
        sa.Column("origem", sa.String(length=20), nullable=False, server_default="portal"),
    )
    op.add_column(
        "solicitacoes_impressao",
        sa.Column("chave_storage", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "solicitacoes_impressao",
        sa.Column("mime", sa.String(length=120), nullable=False, server_default=""),
    )
    op.add_column(
        "solicitacoes_impressao",
        sa.Column("tamanho", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "solicitacoes_impressao",
        sa.Column("media_id", sa.String(length=120), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_solicitacoes_impressao_media_id", "solicitacoes_impressao", ["media_id"]
    )


def downgrade() -> None:
    # Os bytes ficam órfãos em `arquivos_armazenados` — de propósito. Apagá-los aqui
    # destruiria material que a secretaria ainda não imprimiu por causa de um rollback de
    # aplicação; o expurgo por retenção é o caminho para removê-los.
    op.drop_index("ix_solicitacoes_impressao_media_id", table_name="solicitacoes_impressao")
    op.drop_column("solicitacoes_impressao", "media_id")
    op.drop_column("solicitacoes_impressao", "tamanho")
    op.drop_column("solicitacoes_impressao", "mime")
    op.drop_column("solicitacoes_impressao", "chave_storage")
    op.drop_column("solicitacoes_impressao", "origem")

    op.drop_index("ix_professores_ativo", table_name="professores")
    op.drop_column("professores", "ativo")
