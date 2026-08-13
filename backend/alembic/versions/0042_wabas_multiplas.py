"""Várias WABAs: a conta vira entidade e o status do template passa a ser por conta.

O catálogo nasceu com o id da WABA numa variável de ambiente, apoiado numa premissa que
não se sustenta: a de que uma conta comporta o produto inteiro. Não comporta — o cadastro
de números tem teto (§9e.3), e a escola seguinte entra em outra conta.

O que quebrava não era o cadastro, era o **envio**, e de um jeito calado: template é
aprovado **por WABA**, então o ``aviso_reuniao`` aprovado na primeira conta não existe na
segunda. Com o status numa coluna só do template, ``EnviarBroadcast`` lia "aprovado",
liberava o disparo, e a Graph API recusava — a trava que existe justamente para impedir
isso é que dava o aval errado.

Três mudanças:

1. ``wabas`` — a conta vira entidade, com o portfólio (``meta_business_id``) junto, que é
   onde a Meta de fato mede o teto de números e o limite diário.
2. ``tenants.waba_id`` — a escola diz em qual conta o número dela está, e portanto onde
   procurar o catálogo dela.
3. ``template_wabas`` — o status sai do template e passa a ser por (template, conta). O
   texto continua um só: replicar a linha inteira faria de editar um corpo o trabalho de
   manter N cópias em sincronia.

**Migração de dados:** a conta atual é criada a partir de ``META_WABA_ID``; todas as
escolas apontam para ela e todo status existente é copiado para lá — nenhuma aprovação é
perdida. Sem a env, a linha nasce **inativa** e sem id: o estado fica visível no painel
para ser corrigido, em vez de as aprovações sumirem sem aviso.

Revision ID: 0042_wabas_multiplas
Revises: 0041_anti_spam_documentos
Create Date: 2026-08-13
"""

from __future__ import annotations

import os
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "0042_wabas_multiplas"
down_revision = "0041_anti_spam_documentos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wabas",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("meta_waba_id", sa.String(64), nullable=False, unique=True),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("meta_business_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("criado_em", sa.DateTime(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_wabas_meta_waba_id", "wabas", ["meta_waba_id"])

    op.add_column(
        "tenants", sa.Column("waba_id", PGUUID(as_uuid=True), nullable=True)
    )
    op.create_index("ix_tenants_waba_id", "tenants", ["waba_id"])
    op.create_foreign_key(
        "fk_tenants_waba", "tenants", "wabas", ["waba_id"], ["id"]
    )

    op.create_table(
        "template_wabas",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "template_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "waba_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("wabas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("meta_template_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("motivo_rejeicao", sa.Text(), nullable=False, server_default=""),
        sa.Column("atualizado_em", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("template_id", "waba_id", name="uq_template_waba"),
    )
    op.create_index("ix_template_wabas_template_id", "template_wabas", ["template_id"])
    op.create_index("ix_template_wabas_waba_id", "template_wabas", ["waba_id"])
    op.create_index(
        "ix_template_wabas_meta_template_id", "template_wabas", ["meta_template_id"]
    )

    _migrar_conta_atual()

    op.drop_column("templates", "status")
    op.drop_column("templates", "meta_template_id")
    op.drop_column("templates", "motivo_rejeicao")


def _migrar_conta_atual() -> None:
    """Cria a linha da conta em uso e move os status existentes para ela.

    Roda mesmo sem ``META_WABA_ID``: o que não pode acontecer é o catálogo existente ficar
    órfão de conta, porque aí todo template viraria "não submetido" e o produto passaria a
    recusar disparos que hoje funcionam.
    """
    conexao = op.get_bind()

    meta_waba_id = (os.environ.get("META_WABA_ID") or "").strip()
    meta_business_id = (os.environ.get("META_BUSINESS_ID") or "").strip()
    waba_id = uuid.uuid4()

    conexao.execute(
        sa.text(
            "INSERT INTO wabas (id, meta_waba_id, nome, meta_business_id, ativo, criado_em)"
            " VALUES (:id, :meta, :nome, :business, :ativo, NOW())"
        ),
        {
            "id": waba_id,
            "meta": meta_waba_id,
            "nome": "WABA principal",
            "business": meta_business_id,
            # Sem id na Meta não há onde submeter: a conta existe para não órfãos os
            # templates, mas não deve receber replicação até alguém preencher o id.
            "ativo": bool(meta_waba_id),
        },
    )

    conexao.execute(sa.text("UPDATE tenants SET waba_id = :id"), {"id": waba_id})

    linhas = conexao.execute(
        sa.text(
            "SELECT id, status, meta_template_id, motivo_rejeicao FROM templates"
        )
    ).fetchall()
    for linha in linhas:
        conexao.execute(
            sa.text(
                "INSERT INTO template_wabas"
                " (id, template_id, waba_id, status, meta_template_id, motivo_rejeicao,"
                "  atualizado_em)"
                " VALUES (:id, :template, :waba, :status, :meta, :motivo, NOW())"
            ),
            {
                "id": uuid.uuid4(),
                "template": linha[0],
                "waba": waba_id,
                "status": linha[1] or "rascunho",
                "meta": linha[2] or "",
                "motivo": linha[3] or "",
            },
        )


def downgrade() -> None:
    op.add_column(
        "templates",
        sa.Column("status", sa.String(20), nullable=False, server_default="rascunho"),
    )
    op.add_column(
        "templates",
        sa.Column("meta_template_id", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "templates",
        sa.Column("motivo_rejeicao", sa.Text(), nullable=False, server_default=""),
    )

    # Volta o status de **uma** conta para a coluna única. Com mais de uma WABA a
    # informação não cabe no destino, então escolhemos a mais recentemente atualizada —
    # é o retrato menos errado possível, e o downgrade é caminho de emergência.
    op.execute(
        """
        UPDATE templates t
           SET status = tw.status,
               meta_template_id = tw.meta_template_id,
               motivo_rejeicao = tw.motivo_rejeicao
          FROM (
                SELECT DISTINCT ON (template_id)
                       template_id, status, meta_template_id, motivo_rejeicao
                  FROM template_wabas
                 ORDER BY template_id, atualizado_em DESC NULLS LAST
               ) tw
         WHERE tw.template_id = t.id
        """
    )
    op.create_index("ix_templates_meta_template_id", "templates", ["meta_template_id"])

    op.drop_table("template_wabas")
    op.drop_constraint("fk_tenants_waba", "tenants", type_="foreignkey")
    op.drop_index("ix_tenants_waba_id", table_name="tenants")
    op.drop_column("tenants", "waba_id")
    op.drop_table("wabas")
