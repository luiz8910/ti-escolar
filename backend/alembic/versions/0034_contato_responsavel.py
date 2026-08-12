"""Cadastro do responsável e o termo de guarda (Fase 2 do plano de 10/08).

O apontamento, no bloco de Alunos:

> *Cadastro do responsável: Nome\\*, CPF\\*, tipo de filiação, data nascimento,
> telefone_1\\* (principal, será usado nos disparos e na conversa com a IA), telefone_2,
> local de trabalho, telefone_trabalho, email.*
> *Cadastro termo de guarda: mesmos campos — usado quando o responsável não é mãe/pai.*

``Contato`` tinha **nome e telefone**. Ganha aqui o cadastro civil e o vínculo.

**O termo de guarda deixa de ser um booleano.** Ele estava modelado como
``FichaMatricula.termo_guarda`` + ``responsavel_legal`` (um nome solto em texto), o que
deixava a pessoa **invisível para o canal**: não recebia disparo, não era reconhecida no
WhatsApp, não entrava na cobertura de contatos da turma. Agora é um ``Contato`` com
``tipo_filiacao = 'responsavel_legal'`` — igual a qualquer outro responsável, ligado ao
aluno por ``aluno_responsaveis``, que já existe.

**Qual telefone dispara.** ``telefone`` continua sendo o único que roteia inbound e recebe
outbound — é a chave da conversa. ``telefone_2`` e ``telefone_trabalho`` são contato de
emergência e não entram em disparo nenhum (decisão E): dois números na mesma conversa
quebrariam o roteamento, que casa por telefone.

**UNIQUE parcial no CPF**, como em ``professores`` (0032): único por escola quando
informado, e o default ``''`` conviveria mal com um UNIQUE simples.

.. note::
   O id desta revisão nasceu ``0034_contato_cadastro_responsavel`` e **quebrou o deploy**:
   ``alembic_version.version_num`` é ``VARCHAR(32)`` e ele tinha 33 caracteres. O erro
   (``StringDataRightTruncation``) só aparece ao aplicar, nunca ao escrever. Três
   migrations do projeto estão em **exatamente 32** — a régua já estava no limite.

Revision ID: 0034_contato_responsavel
Revises: 0033_usuario_cargo_hierarquia
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0034_contato_responsavel"
down_revision: str | None = "0033_usuario_cargo_hierarquia"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUNAS = (
    ("cpf", sa.String(11)),
    ("tipo_filiacao", sa.String(20)),
    ("data_nascimento", sa.String(10)),
    ("telefone_2", sa.String(50)),
    ("local_trabalho", sa.String(200)),
    ("telefone_trabalho", sa.String(50)),
    ("email", sa.String(200)),
)


def upgrade() -> None:
    for nome, tipo in _COLUNAS:
        op.add_column(
            "contatos", sa.Column(nome, tipo, nullable=False, server_default="")
        )
    op.create_index(
        "uq_contato_tenant_cpf",
        "contatos",
        ["tenant_id", "cpf"],
        unique=True,
        postgresql_where=sa.text("cpf <> ''"),
    )
    # Os responsáveis que já existem ficam com `tipo_filiacao` vazio, e não com um chute
    # de "mãe": o dado não está no banco, e inventá-lo faria a ficha do aluno afirmar um
    # parentesco que ninguém declarou. A tela mostra "—" e a secretaria completa.


def downgrade() -> None:
    op.drop_index("uq_contato_tenant_cpf", table_name="contatos")
    for nome, _ in _COLUNAS:
        op.drop_column("contatos", nome)
