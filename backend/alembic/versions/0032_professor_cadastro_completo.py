"""Cadastro funcional do professor (Fase 2 do plano de correções de 10/08).

``Professor`` nasceu enxuto de propósito — nome e telefone — porque o que existia era o
mural (§A1). Com o cadastro escolar real, a secretaria precisa do registro funcional:
CPF, nascimento, matrícula na rede, endereço, segundo telefone e e-mail.

Dois campos não são cadastro, são **comportamento**:

- ``titular`` distingue o professor da turma do **eventual**. A chamada de eventual (§I1)
  hoje recebe uma lista de telefones digitada à mão a cada aviso de falta; com este campo
  ela passa a sair da base.
- ``educacao_fisica`` fica registrado sem consumidor ainda — a escala de quadra e a
  chamada "estilo Tinder" do apontamento são posteriores.

``telefone_2`` **não** recebe disparo: é contato de emergência. Ver o docstring de
``Professor``.

**UNIQUE parcial no CPF:** único por escola quando informado. Um UNIQUE simples permitiria
um só professor sem CPF, já que o default é ``''`` — mesmo motivo do índice de
``meta_phone_number_id`` (0024).

Revision ID: 0032_professor_cadastro_completo
Revises: 0031_fonte_conhecimento_conteudo
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0032_professor_cadastro_completo"
down_revision: str | None = "0031_fonte_conhecimento_conteudo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUNAS = (
    ("cpf", sa.String(11), "''"),
    ("data_nascimento", sa.String(10), "''"),
    ("matricula", sa.String(50), "''"),
    ("endereco", sa.Text(), "''"),
    ("telefone_2", sa.String(50), "''"),
    ("email", sa.String(200), "''"),
)


def upgrade() -> None:
    for nome, tipo, default in _COLUNAS:
        op.add_column(
            "professores",
            sa.Column(nome, tipo, nullable=False, server_default=sa.text(default)),
        )
    op.add_column(
        "professores",
        sa.Column(
            "educacao_fisica", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    # Quem já está cadastrado é titular: são os professores das turmas do seed e da
    # escola-âncora. Marcar todos como eventuais faria a chamada de falta convocar o
    # professor que está em sala.
    op.add_column(
        "professores",
        sa.Column("titular", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index(
        "uq_professor_tenant_cpf",
        "professores",
        ["tenant_id", "cpf"],
        unique=True,
        postgresql_where=sa.text("cpf <> ''"),
    )


def downgrade() -> None:
    op.drop_index("uq_professor_tenant_cpf", table_name="professores")
    for nome in ("titular", "educacao_fisica", *(c[0] for c in _COLUNAS)):
        op.drop_column("professores", nome)
