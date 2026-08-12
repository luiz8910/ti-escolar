"""Foto do aluno e o estado do laudo médico na ficha (Fase 2 do plano de 10/08).

**Foto (``alunos.foto_chave``).** O apontamento pedia upload de foto no cadastro do aluno.
Guarda só a **chave** no ``ArquivoStorage`` — os bytes ficam onde já ficam os documentos
recebidos (§6k), hoje ``arquivos_armazenados``. Cadastro não é lugar de ``bytea``: separar
é o que permite trocar o armazenamento sem tocar no aluno.

**A foto é opcional** (decisão D). Foto de criança eleva o risco LGPD e um campo
obrigatório travaria o cadastro de quem não a tem no dia da matrícula.

**Laudo (``fichas_matricula``, dentro do JSON ``conteudo``).** A ficha física tem três
caixas — NÃO · SIM (com CID) · EM INVESTIGAÇÃO — e o modelo só tinha ``laudo_cid``, um
texto livre. Texto livre não distingue "não tem laudo" de "está em investigação", e a
diferença importa: uma fecha o assunto, a outra é pendência que a escola acompanha.
``laudo_status`` não precisa de DDL: a ficha é um JSON e o campo entra no
``CAMPOS_FICHA_MATRICULA``. Fica registrado aqui por ser a mesma mudança de produto.

Revision ID: 0035_aluno_foto
Revises: 0034_contato_responsavel
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0035_aluno_foto"
down_revision: str | None = "0034_contato_responsavel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "alunos",
        sa.Column("foto_chave", sa.String(120), nullable=False, server_default=""),
    )


def downgrade() -> None:
    # Derruba a referência, não os bytes: os arquivos continuam em `arquivos_armazenados`
    # e viram órfãos. Apagá-los aqui tornaria o downgrade destrutivo — e um rollback de
    # aplicação não deveria custar as fotos da escola.
    op.drop_column("alunos", "foto_chave")
