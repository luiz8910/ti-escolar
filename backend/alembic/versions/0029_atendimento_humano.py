"""Atendimento humano: fila da secretaria, expediente da escola e autor da mensagem.

Três coisas, uma migration, porque só fazem sentido juntas (§6j):

- **``atendimentos_humanos``** — a fila. Quando o assistente não resolve, ele oferece
  atendimento humano e, com o "sim" do responsável, o caso cai aqui para a secretaria
  assumir. ``ultima_mensagem_responsavel_em`` é o carimbo de que sai a janela de 24h da
  Meta: sem ele o atendente escreve, a Graph API recusa o texto livre e a resposta some.
- **Expediente no ``tenants``** — o horário da secretaria vira **campo**, não texto na base
  de conhecimento. A base responde a quem *pergunta* o horário; aqui o horário decide se o
  assistente promete atendimento agora ou no próximo dia útil, e uma decisão de controle
  não pode depender de o RAG ter recuperado o trecho certo.
- **``mensagens.autor_nome``** — ``autor`` já é ``String(20)`` livre, então ``"atendente"``
  entra sem schema; o que falta é *quem* da secretaria respondeu.

Revision ID: 0029_atendimento_humano
Revises: 0028_aluno_soft_delete
Create Date: 2026-08-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0029_atendimento_humano"
down_revision: str | None = "0028_aluno_soft_delete"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Expediente da secretaria ------------------------------------------------- #
    # Defaults = o expediente da EM Rosa Cury (seg–sex, 7h30–17h). Escola já cadastrada
    # herda um horário plausível em vez de "fechada 24h", que travaria o encaminhamento.
    op.add_column(
        "tenants",
        sa.Column(
            "expediente_dias", sa.String(20), nullable=False, server_default="1,2,3,4,5"
        ),
    )
    op.add_column(
        "tenants",
        sa.Column("expediente_inicio", sa.Time(), nullable=False, server_default="07:30"),
    )
    op.add_column(
        "tenants",
        sa.Column("expediente_fim", sa.Time(), nullable=False, server_default="17:00"),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "expediente_timezone",
            sa.String(64),
            nullable=False,
            server_default="America/Sao_Paulo",
        ),
    )

    # --- Quem respondeu, quando é uma pessoa --------------------------------------- #
    op.add_column(
        "mensagens",
        sa.Column("autor_nome", sa.String(200), nullable=False, server_default=""),
    )

    # --- A fila da secretaria ------------------------------------------------------ #
    op.create_table(
        "atendimentos_humanos",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        # tenant_id e conversa_id não levam índice próprio: são prefixo dos compostos
        # criados abaixo, que o planejador usa igual. Índice a mais aqui só custa escrita
        # numa tabela que recebe uma linha por mensagem encaminhada.
        sa.Column(
            "tenant_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "conversa_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("conversas.id"),
            nullable=False,
        ),
        sa.Column("contato", sa.String(50), nullable=False, index=True),
        sa.Column("contato_nome", sa.String(200), nullable=False, server_default=""),
        sa.Column("motivo", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="oferecido"),
        sa.Column("ofereceu_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fora_expediente", sa.Boolean(), nullable=False, server_default="false"),
        # ON DELETE SET NULL: desligar a funcionária não pode apagar o registro de que ela
        # respondeu ao responsável.
        sa.Column(
            "atendente_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("usuarios.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("atendente_nome", sa.String(200), nullable=False, server_default=""),
        sa.Column(
            "ultima_mensagem_responsavel_em", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("assumido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolvido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
    )
    # A consulta quente é sempre a mesma: a fila aberta de uma escola, mais antiga
    # primeiro. Sem o índice composto, ela varre todos os atendimentos já resolvidos.
    op.create_index(
        "ix_atendimentos_tenant_status_criado",
        "atendimentos_humanos",
        ["tenant_id", "status", "criado_em"],
    )
    # O caminho do inbound consulta "esta conversa tem atendimento na fila?" a **cada**
    # mensagem recebida, antes de decidir se o assistente responde ou fica calado.
    op.create_index(
        "ix_atendimentos_conversa_status",
        "atendimentos_humanos",
        ["conversa_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_atendimentos_conversa_status", table_name="atendimentos_humanos")
    op.drop_index("ix_atendimentos_tenant_status_criado", table_name="atendimentos_humanos")
    op.drop_table("atendimentos_humanos")
    op.drop_column("mensagens", "autor_nome")
    op.drop_column("tenants", "expediente_timezone")
    op.drop_column("tenants", "expediente_fim")
    op.drop_column("tenants", "expediente_inicio")
    op.drop_column("tenants", "expediente_dias")
