"""A conversa vira **sessão** (Fase 3 do plano de correções de 10/08).

Havia uma ``Conversa`` por ``(tenant, contato)``, para sempre — um UNIQUE garantia isso.
Duas consequências, e a segunda custa dinheiro:

1. o histórico do painel virava um fio infinito, impossível de ler;
2. **o contexto enviado à LLM crescia sem limite**: cada mensagem carregava meses de
   assunto encerrado, encarecendo a chamada e piorando a resposta.

Agora a sessão viva é a que não foi encerrada e cuja última mensagem está dentro de
``CONVERSA_JANELA_HORAS`` (24 por padrão — o mesmo relógio da janela da Meta, que é o que
o responsável percebe). Fora disso, a próxima mensagem abre outra.

**O UNIQUE precisa sair**: é justamente ele que impedia a segunda sessão do mesmo
responsável. No lugar entra um índice de busca por ``(tenant, contato, encerrada_em)``,
que é a consulta feita a cada mensagem recebida.

**Backfill.** ``ultima_mensagem_em`` recebe a data da última mensagem de cada conversa (ou
a de criação, para conversa vazia) — inventar "agora" faria toda conversa antiga parecer
viva e continuar acumulando contexto. As conversas cuja última mensagem já passou da
janela nascem **encerradas**: elas já estavam mortas na prática, e mantê-las abertas faria
a primeira mensagem de cada responsável reabrir um fio de meses.

Revision ID: 0037_conversa_sessao
Revises: 0036_turma_estruturada
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0037_conversa_sessao"
down_revision: str | None = "0036_turma_estruturada"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A mesma janela padrão do `Settings.conversa_janela_horas`. Repetida aqui de propósito:
# migration não deve importar config da aplicação — o valor do ambiente pode ter mudado
# desde então, e o backfill precisa ser reprodutível.
_JANELA_HORAS = 24


def upgrade() -> None:
    op.add_column(
        "conversas",
        sa.Column("ultima_mensagem_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversas", sa.Column("encerrada_em", sa.DateTime(timezone=True), nullable=True)
    )

    op.execute(
        """
        UPDATE conversas c
           SET ultima_mensagem_em = COALESCE(
                   (SELECT MAX(m.criado_em) FROM mensagens m WHERE m.conversa_id = c.id),
                   c.criado_em
               )
        """
    )
    # Conversa parada há mais que a janela já estava morta: nasce encerrada, senão a
    # próxima mensagem do responsável reabriria um fio de meses.
    op.execute(
        f"""
        UPDATE conversas
           SET encerrada_em = ultima_mensagem_em
         WHERE ultima_mensagem_em < NOW() - INTERVAL '{_JANELA_HORAS} hours'
        """
    )

    op.drop_constraint("uq_conversa_tenant_contato", "conversas", type_="unique")
    op.create_index(
        "ix_conversa_sessao_viva", "conversas", ["tenant_id", "contato", "encerrada_em"]
    )


def downgrade() -> None:
    op.drop_index("ix_conversa_sessao_viva", table_name="conversas")
    # Atenção: se já houver mais de uma sessão do mesmo responsável, recriar o UNIQUE
    # **falha** — e é o comportamento certo. Escolher qual sessão apagar (e com ela as
    # mensagens trocadas com uma família) não é decisão de migration.
    op.create_unique_constraint(
        "uq_conversa_tenant_contato", "conversas", ["tenant_id", "contato"]
    )
    op.drop_column("conversas", "encerrada_em")
    op.drop_column("conversas", "ultima_mensagem_em")
