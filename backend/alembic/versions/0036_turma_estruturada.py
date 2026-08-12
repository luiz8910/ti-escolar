"""Turma estruturada e o fim do vínculo manual pai↔turma (Fase 2 do plano de 10/08).

**Duas mudanças, e a segunda é a delicada.**

1. A turma passa a ser identificada por ``ano_letivo`` · ``etapa`` · ``turma``, mais
   ``numero_sala``, ``periodo`` e ``grade_horario``. O ``nome`` continua existindo, agora
   derivado, porque relatórios e telas já o exibem. Texto livre impedia ordenar, promover
   série e cruzar com a ficha — e deixava "4ª B", "4ª série B" e "4a serie B" conviverem
   como turmas diferentes, com alunos espalhados entre elas.

   O backfill separa o nome atual em etapa + letra por expressão regular ("4ª série B" →
   etapa "4ª série", turma "B"). O que não casar fica com ``etapa`` = nome inteiro e
   ``turma`` vazia — a turma continua funcionando e a secretaria ajusta na tela. Chutar
   uma letra seria pior: viraria uma turma "A" que ninguém criou.

2. **``sala_contatos`` é removida.** O vínculo pai↔turma passa a ser derivado: um
   responsável pertence à turma porque tem **aluno ativo** nela
   (``aluno_responsaveis`` + ``alunos.sala_id``, que já existem).

   O que se perde ao dropar são exatamente as linhas **erradas**: pai vinculado a uma
   turma onde não tem nenhum filho. Era o estado que fazia a cobertura de contatos
   (§6c-ter) contar errado e que o apontamento mandou tirar da tela. Todo o resto é
   reconstruível — e o ``downgrade`` **recria a tabela já populada** a partir da
   derivação, para um rollback não devolver a escola a uma tela vazia.

Revision ID: 0036_turma_estruturada
Revises: 0035_aluno_foto
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0036_turma_estruturada"
down_revision: str | None = "0035_aluno_foto"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# "4ª série B" / "1º A" / "5 ANO C" → grupo 1 = etapa, grupo 2 = a letra da turma.
# Só uma letra isolada no fim conta como turma: "Turma especial" não vira etapa "Turma
# especia" + turma "L".
_SEPARA_TURMA = r"^\s*(.*\S)\s+([A-Da-d])\s*$"


def upgrade() -> None:
    op.add_column(
        "salas", sa.Column("ano_letivo", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("salas", sa.Column("etapa", sa.String(60), nullable=False, server_default=""))
    op.add_column("salas", sa.Column("turma", sa.String(10), nullable=False, server_default=""))
    op.add_column(
        "salas", sa.Column("numero_sala", sa.String(30), nullable=False, server_default="")
    )
    op.add_column("salas", sa.Column("periodo", sa.String(20), nullable=False, server_default=""))
    op.add_column(
        "salas", sa.Column("grade_horario", sa.JSON(), nullable=False, server_default="{}")
    )

    # Ano letivo corrente para as turmas que já existem: é a informação honesta disponível,
    # e deixá-las em 0 as tiraria da ordenação por ano.
    op.execute("UPDATE salas SET ano_letivo = EXTRACT(YEAR FROM CURRENT_DATE)::int")
    op.execute(
        f"""
        UPDATE salas
           SET etapa = COALESCE(substring(nome FROM '{_SEPARA_TURMA}'), nome),
               turma = UPPER(COALESCE(substring(nome FROM '^.*\\s+([A-Da-d])\\s*$'), ''))
        """
    )
    op.create_unique_constraint(
        "uq_sala_tenant_ano_turma", "salas", ["tenant_id", "ano_letivo", "etapa", "turma"]
    )
    # O UNIQUE antigo em `nome` sai: o nome é derivado de etapa + turma e **se repete
    # legitimamente entre anos letivos** — a "4ª série B" de 2026 e a de 2027 são turmas
    # diferentes, e o índice antigo recusava a segunda. Quem identifica agora é a chave
    # composta acima, que também cobre as turmas antigas (etapa = nome, turma = '').
    op.drop_constraint("uq_sala_tenant_nome", "salas", type_="unique")

    # O vínculo manual sai; a derivação o substitui. Ver o docstring.
    op.drop_table("sala_contatos")


def downgrade() -> None:
    # Atenção: se a escola já tiver a mesma turma em dois anos letivos, recriar este
    # UNIQUE **falha** — e é o comportamento certo. Escolher qual linha apagar para caber
    # no índice antigo não é decisão de migration.
    op.create_unique_constraint("uq_sala_tenant_nome", "salas", ["tenant_id", "nome"])
    op.drop_constraint("uq_sala_tenant_ano_turma", "salas", type_="unique")
    for coluna in ("grade_horario", "periodo", "numero_sala", "turma", "etapa", "ano_letivo"):
        op.drop_column("salas", coluna)

    op.create_table(
        "sala_contatos",
        sa.Column(
            "sala_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("salas.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "contato_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("contatos.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    # Repopula a partir da derivação: um rollback não pode devolver a escola a uma tela
    # vazia de responsáveis por turma.
    op.execute(
        """
        INSERT INTO sala_contatos (sala_id, contato_id)
        SELECT DISTINCT a.sala_id, ar.contato_id
          FROM alunos a
          JOIN aluno_responsaveis ar ON ar.aluno_id = a.id
         WHERE a.ativo IS TRUE
        """
    )
