"""Injeção de dependências: monta casos de uso a partir das fábricas e da sessão de BD."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.admin_use_cases import EnviarBroadcastParaGrupo
from app.application.use_cases import (
    AtenderConversa,
    EnviarBroadcast,
    ReceberMensagemRecebida,
    RecuperarEEnviarDocumento,
    ResponderDuvida,
)
from app.config import Settings, get_settings
from app.infrastructure.db.pgvector_store import PgVectorStore
from app.infrastructure.db.repositories import (
    SqlBroadcastRepository,
    SqlConversaRepository,
    SqlTemplateRepository,
)
from app.application.conhecimento_use_cases import IngerirDocumento
from app.infrastructure.db.repositories_admin import (
    SqlContatoRepository,
    SqlGrupoRepository,
<<<<<<< HEAD
    SqlTenantRepository,
=======
    SqlSalaRepository,
>>>>>>> origin/main
    SqlUsuarioRepository,
)
from app.infrastructure.db.repositories_conhecimento import (
    SqlFonteConhecimentoRepository,
    SqlPromptTenantRepository,
)
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.documents.mock_source import MockDocumentSource
from app.infrastructure.factories import criar_canal, criar_embedder, criar_llm
from app.infrastructure.messaging.quota import SqlQuotaPolicy, TokenBucketRateLimiter

_rate_limiter = TokenBucketRateLimiter(taxa_por_segundo=20.0)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_settings_dep() -> Settings:
    return get_settings()


def get_receber_mensagem(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> ReceberMensagemRecebida:
    embedder = criar_embedder(settings)
    llm = criar_llm(settings)
    canal = criar_canal(settings)
    store = PgVectorStore(session)

    prompts = SqlPromptTenantRepository(session)
    responder = ResponderDuvida(embedder=embedder, store=store, llm=llm, prompts=prompts)
    documentos = RecuperarEEnviarDocumento(source=MockDocumentSource(), canal=canal)
    conversas = SqlConversaRepository(session)
    return ReceberMensagemRecebida(
        conversas=conversas, responder=responder, documentos=documentos
    )


def get_atender_conversa(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> AtenderConversa:
    embedder = criar_embedder(settings)
    llm = criar_llm(settings)
    canal = criar_canal(settings)
    store = PgVectorStore(session)

    documentos = RecuperarEEnviarDocumento(source=MockDocumentSource(), canal=canal)
    return AtenderConversa(
        conversas=SqlConversaRepository(session),
        embedder=embedder,
        store=store,
        llm=llm,
        documentos=documentos,
        prompts=SqlPromptTenantRepository(session),
    )


def get_enviar_broadcast(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> EnviarBroadcast:
    return EnviarBroadcast(
        broadcasts=SqlBroadcastRepository(session),
        templates=SqlTemplateRepository(session),
        canal=criar_canal(settings),
        quota=SqlQuotaPolicy(session, limite_diario=settings.meta_daily_tier_limit),
        rate_limiter=_rate_limiter,
    )


def get_quota_policy(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> SqlQuotaPolicy:
    return SqlQuotaPolicy(session, limite_diario=settings.meta_daily_tier_limit)


# --------------------------------------------------------------------------- #
# Administração e grupos
# --------------------------------------------------------------------------- #
def get_usuario_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlUsuarioRepository:
    return SqlUsuarioRepository(session)


def get_grupo_repo(session: AsyncSession = Depends(get_session)) -> SqlGrupoRepository:
    return SqlGrupoRepository(session)


<<<<<<< HEAD
def get_tenant_repo(session: AsyncSession = Depends(get_session)) -> SqlTenantRepository:
    return SqlTenantRepository(session)


def get_conversa_repo(session: AsyncSession = Depends(get_session)) -> SqlConversaRepository:
    return SqlConversaRepository(session)


def get_broadcast_repo(session: AsyncSession = Depends(get_session)) -> SqlBroadcastRepository:
    return SqlBroadcastRepository(session)
=======
def get_contato_repo(session: AsyncSession = Depends(get_session)) -> SqlContatoRepository:
    return SqlContatoRepository(session)


def get_sala_repo(session: AsyncSession = Depends(get_session)) -> SqlSalaRepository:
    return SqlSalaRepository(session)
>>>>>>> origin/main


def get_enviar_para_grupo(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> EnviarBroadcastParaGrupo:
    enviar = EnviarBroadcast(
        broadcasts=SqlBroadcastRepository(session),
        templates=SqlTemplateRepository(session),
        canal=criar_canal(settings),
        quota=SqlQuotaPolicy(session, limite_diario=settings.meta_daily_tier_limit),
        rate_limiter=_rate_limiter,
    )
    return EnviarBroadcastParaGrupo(grupos=SqlGrupoRepository(session), enviar=enviar)


# --------------------------------------------------------------------------- #
# Base de conhecimento (RAG por tenant) e system prompt por tenant
# --------------------------------------------------------------------------- #
def get_fonte_conhecimento_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlFonteConhecimentoRepository:
    return SqlFonteConhecimentoRepository(session)


def get_prompt_tenant_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlPromptTenantRepository:
    return SqlPromptTenantRepository(session)


def get_ingerir_documento(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> IngerirDocumento:
    return IngerirDocumento(
        embedder=criar_embedder(settings),
        store=PgVectorStore(session),
        fontes=SqlFonteConhecimentoRepository(session),
    )
