"""Texto original e interruptor de indexação na base de conhecimento.

Duas lacunas do mesmo ponto: o documento que a escola sobe era **fragmentado e esquecido**.
Os trechos iam para o vector store, os metadados para ``fontes_conhecimento`` e o texto
original não ficava em lugar nenhum. Consequência prática: a secretaria não conseguia reler
o que tinha enviado nem corrigir uma linha — só apagar e reenviar do zero.

- ``conteudo`` guarda o texto **como foi enviado**, que é o que permite visualizar e editar.
- ``ativo`` separa **existir** de **estar indexado**. Um procedimento que saiu de vigência
  precisa parar de alimentar o bot sem que o texto seja destruído — apagar é do super admin
  (a remoção passou a exigi-lo), desativar é da escola.

``atualizado_em`` nasce igual a ``criado_em`` nas linhas existentes: é a informação honesta
disponível, já que ninguém editou nada antes desta migration.

**Recuperação do texto dos documentos antigos.** As fontes que já existem nasceram sem
``conteudo``, e deixá-las vazias faria a tela nova abri-las em branco — pior que não ter a
tela. Mas o texto não se perdeu: ele está em ``conhecimento``, fragmentado. Como
``fragmentar`` quebra em parágrafos e junta com ``\\n\\n``, recolar os trechos na mesma
ordem reconstrói o documento.

Duas ressalvas ditas de frente: é **reconstrução, não o original byte a byte** (o
agrupamento de parágrafos curtos num mesmo trecho é preservado, mas espaços em branco
extras da ponta foram normalizados na ingestão); e a ordem vem de ``criado_em``, que é
gravado por trecho dentro do laço de indexação — com um ``await`` de banco entre eles,
empate de microssegundo é improvável, e ``id`` desempata de forma estável. Documento de um
trecho só — o caso de toda a base atual — é exato.

Revision ID: 0031_fonte_conhecimento_conteudo
Revises: 0030_documentos_recebidos
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0031_fonte_conhecimento_conteudo"
down_revision: str | None = "0030_documentos_recebidos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fontes_conhecimento",
        sa.Column("conteudo", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "fontes_conhecimento",
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "fontes_conhecimento",
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
    )
    # As fontes que já existem nunca foram editadas: a data de atualização é a de criação.
    op.execute("UPDATE fontes_conhecimento SET atualizado_em = criado_em")

    # Recola o texto a partir dos trechos indexados, para os documentos anteriores a esta
    # migration não abrirem em branco na tela nova. `string_agg` devolve NULL quando a
    # fonte não tem trecho nenhum; `COALESCE` mantém a string vazia nesse caso.
    op.execute(
        """
        UPDATE fontes_conhecimento f
           SET conteudo = COALESCE(t.texto, '')
          FROM (
                SELECT fonte_id,
                       string_agg(conteudo, E'\\n\\n' ORDER BY criado_em, id) AS texto
                  FROM conhecimento
                 WHERE fonte_id IS NOT NULL
              GROUP BY fonte_id
               ) AS t
         WHERE t.fonte_id = f.id
        """
    )


def downgrade() -> None:
    # Atenção: derruba o texto original das fontes já enviadas. Elas continuam indexadas no
    # vector store, mas voltam a ser ilegíveis pelo painel — que era o estado anterior.
    op.drop_column("fontes_conhecimento", "atualizado_em")
    op.drop_column("fontes_conhecimento", "ativo")
    op.drop_column("fontes_conhecimento", "conteudo")
