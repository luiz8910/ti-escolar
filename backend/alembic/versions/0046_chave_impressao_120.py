"""Alarga ``solicitacoes_impressao.chave_storage`` para caber o prefixo por tenant.

A chave de um arquivo passou a nascer com finalidade e tenant no prefixo —
``impressao/{tenant_id}/2026/08/{token}`` —, e isso não é organização de pasta: é o que
decide o que a regra de lifecycle do bucket apaga. Enquanto os arquivos da fila dividiam o
prefixo ``doc/`` com os documentos dos responsáveis, a regra de 395 dias feita para estes
apagaria também aqueles, que não têm ``expira_em`` nem expurgo de aplicação — e a linha em
``solicitacoes_impressao`` continuaria apontando para um objeto inexistente, devolvendo 404
no download.

A coluna tinha 64 caracteres e a chave nova tem 87. As demais já nasceram com 120
(``documentos_recebidos.chave_storage``, ``alunos.foto_chave``, ``arquivos_armazenados``),
então só esta precisa crescer. As chaves antigas continuam válidas: alargar não as toca.

Revision ID: 0046_chave_impressao
Revises: 0045_dest_tentativas
Create Date: 2026-08-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0046_chave_impressao"
down_revision = "0045_dest_tentativas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "solicitacoes_impressao",
        "chave_storage",
        existing_type=sa.String(length=64),
        type_=sa.String(length=120),
        existing_nullable=False,
        existing_server_default="",
    )


def downgrade() -> None:
    # Estreitar de volta trunca chave nova e quebra o download. O downgrade existe para a
    # cadeia ficar completa; usá-lo com dados novos é perder o ponteiro do arquivo.
    op.alter_column(
        "solicitacoes_impressao",
        "chave_storage",
        existing_type=sa.String(length=120),
        type_=sa.String(length=64),
        existing_nullable=False,
        existing_server_default="",
    )
