"""Soft delete de aluno: alunos.desativado_em e alunos.motivo_desativacao.

O painel excluía aluno de verdade (``DELETE FROM alunos``), e a exclusão de uma série sem
destino apagava os alunos dela junto. Isso destrói o **lastro** de que aquele aluno
estudou na escola — que é exatamente o que ela precisa preservar para histórico escolar,
declarações e prestação de contas.

A flag ``ativo`` já existia (ex-aluno); faltava registrar **quando** e **por quê**, sem o
que "aluno inativo" não distingue transferência de erro de digitação.

Revision ID: 0028_aluno_soft_delete
Revises: 0027_logs_aplicacao
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028_aluno_soft_delete"
down_revision: str | None = "0027_logs_aplicacao"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # timezone=True para casar com alunos.criado_em: misturar naive e aware na mesma
    # tabela produz comparações que falham em runtime, não no schema.
    op.add_column(
        "alunos", sa.Column("desativado_em", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "alunos",
        sa.Column("motivo_desativacao", sa.String(200), nullable=False, server_default=""),
    )
    # Índice parcial: a listagem padrão do painel é "só os matriculados", e os ex-alunos
    # tendem a acumular ano após ano.
    op.create_index(
        "ix_alunos_tenant_ativos",
        "alunos",
        ["tenant_id"],
        postgresql_where=sa.text("ativo"),
    )


def downgrade() -> None:
    op.drop_index("ix_alunos_tenant_ativos", table_name="alunos")
    op.drop_column("alunos", "motivo_desativacao")
    op.drop_column("alunos", "desativado_em")
