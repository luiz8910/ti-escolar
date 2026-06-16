"""Seed de demonstração: escola, conhecimento (RAG indexado) e template aprovado.

Idempotente: usa um tenant fixo (DEMO_TENANT_ID) e não duplica se já existir.
Executado pelo docker-compose após as migrations.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.application.admin_use_cases import CriarGrupo
from app.application.cadastro_use_cases import CadastrarPai, CriarSala
from app.application.use_cases import IndexarConhecimento
from app.config import get_settings
from app.domain.entities import Papel, TipoConhecimento, Usuario
from app.infrastructure.db.models import TemplateORM, TenantORM, UsuarioORM
from app.infrastructure.db.pgvector_store import PgVectorStore
from app.infrastructure.db.repositories_admin import (
    SqlContatoRepository,
    SqlGrupoRepository,
    SqlSalaRepository,
    SqlUsuarioRepository,
)
from app.infrastructure.db.repositories_conhecimento import SqlPromptTenantRepository
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.factories import criar_embedder
from app.infrastructure.security import hash_senha

# Tenant fixo para o demo (o front-end usa este id).
DEMO_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEMO_TEMPLATE_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a1")

# Grupos de demonstração e seus contatos (nome, telefone E.164).
_GRUPOS_DEMO = {
    "Turma 5º A": [
        ("Maria Souza", "+5511999990001"),
        ("João Pereira", "+5511999990002"),
        ("Ana Lima", "+5511999990003"),
    ],
    "Pais do Fundamental I": [
        ("Carlos Mendes", "+5511999990004"),
        ("Patrícia Rocha", "+5511999990005"),
    ],
}

# Salas (turmas) de demonstração e seus pais/responsáveis (nome, telefone E.164).
_SALAS_DEMO = {
    "4ª série B": [
        ("Beatriz Almeida", "+5511988880001"),
        ("Rafael Nogueira", "+5511988880002"),
    ],
    "5ª série A": [
        ("Cláudia Fonseca", "+5511988880003"),
        ("Eduardo Tavares", "+5511988880004"),
    ],
}

# System prompt personalizado do tenant demo (o "CLAUDE.md" da escola).
_PROMPT_DEMO = (
    "Esta é a Escola Demonstração. Trate os responsáveis pelo primeiro nome quando souber. "
    "Reforce sempre o uso obrigatório do uniforme e o e-mail da secretaria "
    "(secretaria@escola.test) para assuntos formais. Em caso de emergência, oriente a ligar "
    "para a portaria. Nunca compartilhe notas ou dados de um aluno com quem não seja o "
    "responsável cadastrado."
)

_CONHECIMENTO = [
    (
        TipoConhecimento.PROCEDIMENTO,
        "Horário de funcionamento",
        "A secretaria atende de segunda a sexta-feira, das 7h30 às 17h. "
        "As aulas do período da manhã começam às 7h30 e as do período da tarde às 13h.",
    ),
    (
        TipoConhecimento.PROCEDIMENTO,
        "Como justificar faltas",
        "Para justificar a falta do aluno, o responsável deve enviar atestado ou justificativa "
        "à secretaria em até 48 horas, presencialmente ou pelo e-mail secretaria@escola.test.",
    ),
    (
        TipoConhecimento.PROCEDIMENTO,
        "Segunda via de boletim e declarações",
        "Boletins, declarações de matrícula e históricos podem ser solicitados pelo WhatsApp. "
        "Basta pedir o documento desejado que enviaremos o arquivo em PDF.",
    ),
    (
        TipoConhecimento.AVISO,
        "Reunião de pais e mestres",
        "A próxima reunião de pais e mestres será no dia 20 de junho, às 19h, no auditório. "
        "A presença dos responsáveis é muito importante.",
    ),
    (
        TipoConhecimento.AVISO,
        "Calendário de provas",
        "As provas do segundo bimestre ocorrerão entre 1º e 5 de julho. "
        "O calendário detalhado por turma está disponível na secretaria.",
    ),
    (
        TipoConhecimento.FAQ,
        "Uniforme escolar",
        "O uso do uniforme é obrigatório. O kit pode ser adquirido na loja parceira indicada "
        "na secretaria. Em dias de educação física, usar o uniforme esportivo.",
    ),
]


async def _seed() -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        # Tenant
        tenant = await session.get(TenantORM, DEMO_TENANT_ID)
        if tenant is None:
            session.add(
                TenantORM(
                    id=DEMO_TENANT_ID,
                    nome="Escola Demonstração",
                    slug="escola-demo",
                    criado_em=datetime.now(timezone.utc),
                )
            )
            await session.flush()

        # Conhecimento (RAG) — só indexa se ainda não houver
        store = PgVectorStore(session)
        indexar = IndexarConhecimento(embedder=criar_embedder(settings), store=store)
        from app.infrastructure.db.models import ConhecimentoORM

        existe = (
            await session.execute(
                select(ConhecimentoORM).where(ConhecimentoORM.tenant_id == DEMO_TENANT_ID).limit(1)
            )
        ).scalar_one_or_none()
        if existe is None:
            for tipo, titulo, conteudo in _CONHECIMENTO:
                await indexar.executar(
                    tenant_id=DEMO_TENANT_ID, tipo=tipo, titulo=titulo, conteudo=conteudo
                )

        # Template aprovado para broadcasts
        template = await session.get(TemplateORM, DEMO_TEMPLATE_ID)
        if template is None:
            session.add(
                TemplateORM(
                    id=DEMO_TEMPLATE_ID,
                    tenant_id=DEMO_TENANT_ID,
                    nome="aviso_reuniao",
                    categoria="utility",
                    idioma="pt_BR",
                    corpo="Olá, {{1}}! Lembrete: {{2}}. Atenciosamente, Escola Demonstração.",
                    status="aprovado",
                )
            )

        # Usuários administrativos (super admin + admin do tenant demo)
        usuarios = SqlUsuarioRepository(session)
        if await usuarios.por_email(settings.super_admin_email) is None:
            await usuarios.criar(
                Usuario(
                    nome=settings.super_admin_nome,
                    email=settings.super_admin_email,
                    senha_hash=hash_senha(settings.super_admin_senha),
                    papel=Papel.SUPER_ADMIN,
                    tenant_id=None,
                )
            )
        if await usuarios.por_email(settings.demo_admin_email) is None:
            await usuarios.criar(
                Usuario(
                    nome="Admin Escola Demonstração",
                    email=settings.demo_admin_email,
                    senha_hash=hash_senha(settings.demo_admin_senha),
                    papel=Papel.TENANT_ADMIN,
                    tenant_id=DEMO_TENANT_ID,
                )
            )

        # Grupos de contatos (pais) — só cria se ainda não houver grupos no tenant
        grupos_repo = SqlGrupoRepository(session)
        if not await grupos_repo.listar(tenant_id=DEMO_TENANT_ID):
            criar_grupo = CriarGrupo(grupos=grupos_repo)
            for nome_grupo, contatos in _GRUPOS_DEMO.items():
                grupo = await criar_grupo.executar(tenant_id=DEMO_TENANT_ID, nome=nome_grupo)
                for nome, telefone in contatos:
                    await grupos_repo.adicionar_contato(
                        tenant_id=DEMO_TENANT_ID,
                        grupo_id=grupo.id,
                        nome=nome,
                        telefone=telefone,
                    )

        # Salas (turmas) com pais/responsáveis vinculados — só cria se ainda não houver
        salas_repo = SqlSalaRepository(session)
        contatos_repo = SqlContatoRepository(session)
        if not await salas_repo.listar(tenant_id=DEMO_TENANT_ID):
            criar_sala = CriarSala(salas=salas_repo)
            cadastrar_pai = CadastrarPai(contatos=contatos_repo, salas=salas_repo)
            for nome_sala, responsaveis in _SALAS_DEMO.items():
                sala = await criar_sala.executar(tenant_id=DEMO_TENANT_ID, nome=nome_sala)
                for nome, telefone in responsaveis:
                    existente = await contatos_repo.por_telefone(
                        tenant_id=DEMO_TENANT_ID, telefone=telefone
                    )
                    if existente is None:
                        await cadastrar_pai.executar(
                            tenant_id=DEMO_TENANT_ID,
                            nome=nome,
                            telefone=telefone,
                            sala_ids=[sala.id],
                        )
                    else:
                        await salas_repo.vincular_pai(
                            tenant_id=DEMO_TENANT_ID,
                            sala_id=sala.id,
                            contato_id=existente.id,
                        )

        # System prompt do tenant demo — só define se ainda não houver um
        prompts_repo = SqlPromptTenantRepository(session)
        if await prompts_repo.obter(tenant_id=DEMO_TENANT_ID) is None:
            await prompts_repo.salvar(tenant_id=DEMO_TENANT_ID, conteudo=_PROMPT_DEMO)

        await session.commit()
    print("Seed concluído (tenant demo:", DEMO_TENANT_ID, ")")
    print("  super admin:", settings.super_admin_email)
    print("  admin tenant demo:", settings.demo_admin_email)


if __name__ == "__main__":
    asyncio.run(_seed())
