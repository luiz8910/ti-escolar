"""Anti-spam dos documentos recebidos (§4.5, Fase 4 do plano de 10/08).

O inbound é **público**: quem descobre o número da escola manda o que quiser. As defesas
que existiam olhavam o envelope (MIME, 16 MB) — nenhuma olhava **de quem** vinha nem
**quantas vezes**.

Duas camadas entram aqui, da mais barata para a mais cara:

1. **Quarentena por origem desconhecida.** Arquivo de telefone sem ``Contato`` na escola
   entra com ``status = 'quarentena'``: fica **fora da fila de trabalho**, mas é guardado.
   Custo zero e resolve o caso mais comum — número aleatório. Não descartamos de saída
   porque pode ser um pai que trocou de número, e aí perderíamos o documento de quem mais
   precisa dele.

2. **Reincidência** (``numeros_bloqueados``). Bloqueia a **mídia**, não a pessoa: o número
   segue sendo atendido em texto, e o remetente é avisado. O bloqueio é sempre **humano**
   — a aplicação só *sugere*, ao cruzar o limiar de 3 descartes em 7 dias (decisão C).
   Bloqueio automático é perigoso aqui: um pai que manda três fotos tremidas do mesmo
   atestado é indistinguível de spam para um contador.

A terceira camada — classificar o **conteúdo** — só faz sentido depois do OCR (§4.3);
antes disso, "não relacionado" seria chute.

Revision ID: 0038_anti_spam_docs
Revises: 0037_conversa_sessao
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0038_anti_spam_docs"
down_revision: str | None = "0037_conversa_sessao"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "numeros_bloqueados",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("telefone", sa.String(50), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False, server_default=""),
        sa.Column("bloqueado_por", sa.String(200), nullable=False, server_default=""),
        sa.Column("bloqueado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "telefone", name="uq_numero_bloqueado_tenant"),
    )
    op.create_index("ix_numeros_bloqueados_tenant_id", "numeros_bloqueados", ["tenant_id"])
    op.create_index("ix_numeros_bloqueados_telefone", "numeros_bloqueados", ["telefone"])
    # `status = 'quarentena'` não exige DDL: a coluna já é String. Fica registrado aqui por
    # ser a mesma mudança de produto.


def downgrade() -> None:
    # Os documentos em quarentena voltam para a fila de trabalho: sem o status, deixá-los
    # invisíveis seria pior — a secretaria não saberia que existem.
    op.execute("UPDATE documentos_recebidos SET status = 'recebido' WHERE status = 'quarentena'")
    op.drop_index("ix_numeros_bloqueados_telefone", table_name="numeros_bloqueados")
    op.drop_index("ix_numeros_bloqueados_tenant_id", table_name="numeros_bloqueados")
    op.drop_table("numeros_bloqueados")
