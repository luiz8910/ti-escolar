"""Catálogo de templates: escopo global, id da Meta e ciclo de revisão.

O template deixa de ser uma linha morta preenchida à mão e passa a espelhar o que existe
na Meta. Quatro mudanças:

1. **``tenant_id`` vira anulável** — nulo = template **global**. Templates moram na WABA,
   que na nossa topologia é uma só para todas as escolas (§9e), e o nome é único nela.
   Um ``aviso_geral`` por escola significaria N revisões da Meta para o mesmo texto e N
   chances de rejeição num ativo compartilhado.

2. **``meta_template_id``** — a chave que o webhook ``message_template_status_update``
   devolve. Sem ela a única forma de casar o evento com a nossa linha seria o nome, que
   funciona mas quebra no dia em que a Meta mandar o evento sem ele.

3. **``motivo_rejeicao``** — "rejeitado" sem motivo é um estado em que a secretaria
   resubmete o mesmo erro.

4. **UNIQUE (nome, idioma)** — espelha a restrição da WABA. Transforma um erro genérico da
   Graph API, descoberto só na submissão, em recusa local com mensagem em português.

⚠️ O ``UPDATE`` que promove ``aviso_reuniao`` e ``retomada_atendimento`` a globais mexe em
dado, e mexe de propósito: são as duas linhas que o seed cria e que passam a ser catálogo
compartilhado. Em produção a tabela está vazia (nenhum template foi cadastrado ainda), de
modo que na prática isto só arruma bancos de desenvolvimento — sem ele, o template do seed
continuaria preso ao tenant demo e invisível para qualquer outra escola.

⚠️ **Numerada 0040 com `down_revision` em 0037, e isso é intencional.** Há hoje três
migrations em voo, todas encadeadas na 0037: `0038_impressao_whatsapp` (PR #56),
`0039`/`0038_anti_spam_docs` (branch `feat/documentos-busca-preview-ocr`) e esta. O número
reserva o lugar na ordem esperada de merge; **o que define o grafo é o `down_revision`**, e
ele precisa continuar apontando para o head da `main` enquanto as outras não entrarem —
apontar para uma revisão que ainda não existe faria `alembic upgrade head` falhar no CI
desta branch.

**Ao mergear:** se alguma das outras já estiver na `main`, re-aponte o `down_revision` desta
para o head novo antes do merge. O CI recusa mais de um head (`alembic heads`), então o
esquecimento falha o build em vez de quebrar o deploy — que é exatamente o que a regra de
cadeia linear do CLAUDE.md §6 existe para evitar.

Revision ID: 0040_templates_catalogo
Revises: 0037_conversa_sessao
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0040_templates_catalogo"
down_revision: str | None = "0037_conversa_sessao"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GLOBAIS = ("aviso_reuniao", "retomada_atendimento")


def upgrade() -> None:
    op.alter_column(
        "templates",
        "tenant_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.add_column(
        "templates",
        sa.Column("meta_template_id", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "templates",
        sa.Column("motivo_rejeicao", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "templates",
        sa.Column("exemplos", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column("templates", sa.Column("criado_em", sa.DateTime(), nullable=True))
    op.add_column("templates", sa.Column("atualizado_em", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_templates_meta_template_id", "templates", ["meta_template_id"]
    )

    # Data de criação das linhas antigas: sem isto a listagem ordenada por data põe os
    # templates existentes em posição arbitrária.
    op.execute("UPDATE templates SET criado_em = NOW() WHERE criado_em IS NULL")

    # Promove os templates do seed a globais (ver o cabeçalho).
    nomes = ", ".join(f"'{n}'" for n in _GLOBAIS)
    op.execute(f"UPDATE templates SET tenant_id = NULL WHERE nome IN ({nomes})")

    # O UNIQUE só entra depois da promoção: duas escolas com o mesmo nome (estado
    # possível no modelo antigo) fariam a criação do índice falhar no meio do deploy.
    op.execute(
        """
        DELETE FROM templates t
        USING templates outro
        WHERE t.nome = outro.nome
          AND t.idioma = outro.idioma
          AND t.tenant_id IS NOT NULL
          AND outro.tenant_id IS NULL
        """
    )
    op.create_unique_constraint(
        "uq_template_nome_idioma", "templates", ["nome", "idioma"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_template_nome_idioma", "templates", type_="unique")
    op.drop_index("ix_templates_meta_template_id", table_name="templates")
    op.drop_column("templates", "atualizado_em")
    op.drop_column("templates", "criado_em")
    op.drop_column("templates", "exemplos")
    op.drop_column("templates", "motivo_rejeicao")
    op.drop_column("templates", "meta_template_id")

    # ``tenant_id`` volta a ser obrigatório, então os globais precisam de dono. Não há
    # escolha certa aqui — o conceito "global" não existe no esquema antigo —, e a menos
    # ruim é apagá-los: manter, atribuindo a uma escola arbitrária, faria a escola sorteada
    # aparecer como dona de um template que ela não criou.
    op.execute("DELETE FROM templates WHERE tenant_id IS NULL")
    op.alter_column(
        "templates",
        "tenant_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
