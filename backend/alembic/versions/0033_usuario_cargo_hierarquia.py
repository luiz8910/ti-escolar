"""Cargo, hierarquia e contato dos usuários da escola (Fase 2 do plano de 10/08).

O apontamento: *"Ter login para secretaria, diretor, vice-diretor e coordenador com número
de whatsapp, endereço completo, email, senha, nome e cargo, expediente/turno. Com exceção
da secretaria os usuários são admins da escola e podem add/remover usuários, observar
hierarquia dos cargos mencionados."*

Três coisas entram:

- **``cargo``** — o posto na escola, que **ordena a hierarquia**: diretor > vice-diretor >
  coordenador > secretaria. Um usuário só gere quem está estritamente abaixo.
- **``papel`` ganha o valor ``secretaria``** — a fronteira de autorização. É papel próprio,
  e não um ``tenant_admin`` com um campo a mais, para falhar **fechado**: uma rota que só
  pergunte "é tenant_admin?" recusa a secretaria por construção.
- **contato** (``telefone``, ``endereco``, ``turno``). O ``telefone`` é o que faltava para
  a fila de atendimento (§6j) notificar por WhatsApp em vez de só pelo badge no painel.

**Migração de dados — os já cadastrados viram diretores.** Hoje todo ``tenant_admin`` pode
tudo dentro da escola; atribuir qualquer cargo menor tiraria acesso de quem tem acesso
agora, no primeiro deploy, sem aviso. Quem for realmente coordenador ou secretaria é
ajustado pela tela de equipe depois — rebaixar é seguro, perder acesso não é.

Revision ID: 0033_usuario_cargo_hierarquia
Revises: 0032_professor_cadastro_completo
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0033_usuario_cargo_hierarquia"
down_revision: str | None = "0032_professor_cadastro_completo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "usuarios", sa.Column("cargo", sa.String(20), nullable=False, server_default="")
    )
    op.add_column(
        "usuarios",
        sa.Column("telefone", sa.String(30), nullable=False, server_default=""),
    )
    op.add_column(
        "usuarios", sa.Column("endereco", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "usuarios", sa.Column("turno", sa.String(20), nullable=False, server_default="")
    )
    # Ver o docstring: quem já administra a escola continua no topo da hierarquia.
    # O super admin fica com cargo vazio — não ocupa posto em escola nenhuma.
    op.execute("UPDATE usuarios SET cargo = 'diretor' WHERE papel = 'tenant_admin'")


def downgrade() -> None:
    # Reverter devolve a secretaria a admin de escola: sem a coluna `cargo` não há como
    # distinguir os papéis, e deixá-la com papel "secretaria" a trancaria fora do painel.
    op.execute("UPDATE usuarios SET papel = 'tenant_admin' WHERE papel = 'secretaria'")
    for coluna in ("turno", "endereco", "telefone", "cargo"):
        op.drop_column("usuarios", coluna)
