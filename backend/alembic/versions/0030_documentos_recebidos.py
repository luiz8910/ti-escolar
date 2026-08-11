"""Documentos que os responsáveis enviam pelo WhatsApp (§6k).

A dor é de época de matrícula: hoje o atestado, o RG e o comprovante chegam no celular de
alguém da secretaria e viram responsabilidade pessoal daquela pessoa — se ela falta, o
documento some. Aqui o arquivo passa a pertencer à escola, ligado à conversa que o
originou.

**Duas tabelas, de propósito:**

- ``documentos_recebidos`` é **negócio** — o que a secretaria consulta, classifica e
  vincula a um aluno. Fica no Postgres para sempre.
- ``arquivos_armazenados`` é **infraestrutura** — os bytes, hoje em ``bytea`` porque não há
  object storage. Some inteira no dia em que o ``ArquivoStorage`` virar R2, sem tocar nos
  metadados. Guardar atestado médico num banco cobrado por GB é aceitável para começar,
  não para sempre.

``expira_em`` nasce preenchido: atestado médico é dado de saúde de criança (LGPD arts. 11 e
14), e sem prazo de retenção um repositório desses vira passivo permanente.

Revision ID: 0030_documentos_recebidos
Revises: 0029_atendimento_humano
Create Date: 2026-08-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0030_documentos_recebidos"
down_revision: str | None = "0029_atendimento_humano"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "arquivos_armazenados",
        sa.Column("chave", sa.String(120), primary_key=True),
        sa.Column("conteudo", sa.LargeBinary(), nullable=False),
        sa.Column("mime", sa.String(120), nullable=False, server_default=""),
        sa.Column("tamanho", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "documentos_recebidos",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column(
            "conversa_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("conversas.id"),
            nullable=False,
        ),
        sa.Column("contato", sa.String(50), nullable=False, index=True),
        sa.Column("contato_nome", sa.String(200), nullable=False, server_default=""),
        sa.Column("chave_storage", sa.String(120), nullable=False),
        sa.Column("mime", sa.String(120), nullable=False),
        sa.Column("tamanho", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nome_arquivo", sa.String(300), nullable=False, server_default=""),
        sa.Column("observacao", sa.Text(), nullable=False, server_default=""),
        sa.Column("categoria", sa.String(20), nullable=False, server_default="outro"),
        sa.Column("categoria_sugerida", sa.String(20), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="recebido"),
        # SET NULL nos dois vínculos: desfazer a ligação não pode apagar a prova de que o
        # documento chegou.
        sa.Column(
            "aluno_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("alunos.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("aluno_nome", sa.String(200), nullable=False, server_default=""),
        sa.Column(
            "atendimento_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("atendimentos_humanos.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("media_id", sa.String(120), nullable=False, server_default=""),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_documentos_tenant_criado", "documentos_recebidos", ["tenant_id", "criado_em"]
    )
    op.create_index(
        "ix_documentos_tenant_media", "documentos_recebidos", ["tenant_id", "media_id"]
    )
    # O expurgo roda cross-tenant e só olha o prazo — daí o índice isolado.
    op.create_index("ix_documentos_expira_em", "documentos_recebidos", ["expira_em"])


def downgrade() -> None:
    op.drop_index("ix_documentos_expira_em", table_name="documentos_recebidos")
    op.drop_index("ix_documentos_tenant_media", table_name="documentos_recebidos")
    op.drop_index("ix_documentos_tenant_criado", table_name="documentos_recebidos")
    op.drop_table("documentos_recebidos")
    op.drop_table("arquivos_armazenados")
