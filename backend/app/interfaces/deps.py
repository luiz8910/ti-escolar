"""Injeção de dependências: monta casos de uso a partir das fábricas e da sessão de BD."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.admin_use_cases import EnviarBroadcastParaGrupo
from app.application.inbound_use_cases import ProcessarInboundMeta
from app.application.tenant_use_cases import NotificarLicencasAVencer
from app.application.atendimento_humano_use_cases import (
    MesaDeAtendimento,
    ResponderAtendimento,
)
from app.application.documentos_use_cases import (
    BaixarDocumentoRecebido,
    ExpurgarDocumentosVencidos,
    ReceberDocumentoDoResponsavel,
    ReceberMidiaDoResponsavel,
)
from app.application.use_cases import (
    AtenderConversa,
    EnviarBroadcast,
    RecuperarEEnviarDocumento,
)
from app.config import Settings, get_settings
from app.domain.ports import LLMProvider, MessageChannel
from app.infrastructure.db.pgvector_store import PgVectorStore
from app.infrastructure.db.repositories import (
    SqlBroadcastRepository,
    SqlConversaRepository,
    SqlTemplateRepository,
)
from app.application.conhecimento_use_cases import (
    AtualizarFonteConhecimento,
    DefinirAtivoFonteConhecimento,
    IngerirDocumento,
)
from app.infrastructure.db.repositories_admin import (
    SqlAlunoRepository,
    SqlAuditLogRepository,
    SqlContatoRepository,
    SqlGrupoRepository,
    SqlProfessorRepository,
    SqlSalaRepository,
    SqlTenantRepository,
    SqlUsuarioRepository,
)
from app.infrastructure.db.repositories_comunicacao import (
    SqlAtendimentoHumanoRepository,
    SqlDocumentoRecebidoRepository,
    SqlAvisoTemporizadoRepository,
    SqlCotaImpressaoRepository,
    SqlMediacaoRepository,
    SqlMuralRepository,
    SqlSolicitacaoImpressaoRepository,
    SqlSolicitacaoInternaRepository,
)
from app.infrastructure.db.repositories_conhecimento import (
    SqlFonteConhecimentoRepository,
    SqlPromptTenantRepository,
    SqlRespostaRapidaRepository,
)
from app.infrastructure.db.repositories_onda3 import (
    SqlAvisoFaltaRepository,
    SqlFichaMatriculaRepository,
    SqlSolicitacaoMatriculaRepository,
)
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.documents.mock_source import MockDocumentSource
from app.infrastructure.factories import (
    criar_canal,
    criar_email_sender,
    criar_fonte_midia,
    criar_embedder,
    criar_llm,
)
from app.infrastructure.atendimento import SqlRegistroAtendimento
from app.infrastructure.messaging.quota import SqlQuotaPolicy, TokenBucketRateLimiter
from app.infrastructure.storage import PostgresArquivoStorage
from app.infrastructure.rate_limit import SqlControleTaxa

_rate_limiter = TokenBucketRateLimiter(taxa_por_segundo=20.0)
# Limite de taxa de ENTRADA (login, inbound). O estado fica no Postgres, então este objeto
# é só o adaptador — pode ser compartilhado entre requisições e réplicas sem problema.
_controle_taxa = SqlControleTaxa(SessionLocal)
# Estado do atendimento do inbound: também no Postgres, porque a reentrega da Meta chega
# durante a espera pela LLM e, com mais de uma réplica, quase sempre em outro processo.
_atendimentos_inbound = SqlRegistroAtendimento(SessionLocal)


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


def get_mesa_atendimento(session: AsyncSession) -> MesaDeAtendimento:
    """Atendimento humano (§6j) — o que o assistente usa para chamar a secretaria."""
    return MesaDeAtendimento(
        atendimentos=SqlAtendimentoHumanoRepository(session),
        tenants=SqlTenantRepository(session),
        contatos=SqlContatoRepository(session),
    )


def get_recepcao_documentos(
    session: AsyncSession, settings: Settings
) -> ReceberDocumentoDoResponsavel:
    """Persistência de um arquivo recebido: metadados no Postgres, bytes no storage."""
    return ReceberDocumentoDoResponsavel(
        documentos=SqlDocumentoRecebidoRepository(session),
        storage=PostgresArquivoStorage(session),
        contatos=SqlContatoRepository(session),
        retencao_dias=settings.documento_retencao_dias,
    )


def get_receber_midia(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> ReceberMidiaDoResponsavel:
    """Arquivo enviado pelo responsável pelo WhatsApp (§6k): baixa, guarda e confirma."""
    return ReceberMidiaDoResponsavel(
        fonte=criar_fonte_midia(settings),
        recepcao=get_recepcao_documentos(session, settings),
        conversas=SqlConversaRepository(session),
        mesa=get_mesa_atendimento(session),
    )


def get_documento_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlDocumentoRecebidoRepository:
    return SqlDocumentoRecebidoRepository(session)


def get_baixar_documento(
    session: AsyncSession = Depends(get_session),
) -> BaixarDocumentoRecebido:
    return BaixarDocumentoRecebido(
        documentos=SqlDocumentoRecebidoRepository(session),
        storage=PostgresArquivoStorage(session),
    )


def get_expurgar_documentos(
    session: AsyncSession = Depends(get_session),
) -> ExpurgarDocumentosVencidos:
    return ExpurgarDocumentosVencidos(
        documentos=SqlDocumentoRecebidoRepository(session),
        storage=PostgresArquivoStorage(session),
    )


def get_processar_inbound_meta(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> ProcessarInboundMeta:
    """Inbound do webhook da Meta: roteia a mensagem à escola e responde por ela (§9e.1)."""
    return ProcessarInboundMeta(
        tenants=SqlTenantRepository(session),
        # O inbound real atende por ``AtenderConversa`` (tool use): é o modelo que decide
        # buscar conhecimento, recuperar documento ou chamar a secretaria — e é esse
        # caminho que registra a resposta da LLM na auditoria (§13).
        atender=get_atender_conversa(session=session, settings=settings),
        canal=criar_canal(settings),
        atendimentos=_atendimentos_inbound,
        midias=get_receber_midia(session=session, settings=settings),
        controle_taxa=_controle_taxa,
        limite_por_remetente=(
            settings.rate_limit_inbound_mensagens if settings.rate_limit_habilitado else 0
        ),
        janela_taxa_segundos=settings.rate_limit_inbound_janela_segundos,
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
        auditoria=SqlAuditLogRepository(session),
        avisos=SqlAvisoTemporizadoRepository(session),
        mesa=get_mesa_atendimento(session),
        max_chars=settings.mensagem_pai_max_chars,
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
        tenants=SqlTenantRepository(session),
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


def get_tenant_repo(session: AsyncSession = Depends(get_session)) -> SqlTenantRepository:
    return SqlTenantRepository(session)


def get_notificar_licencas(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> NotificarLicencasAVencer:
    return NotificarLicencasAVencer(
        tenants=SqlTenantRepository(session),
        usuarios=SqlUsuarioRepository(session),
        emails=criar_email_sender(settings),
    )


def get_conversa_repo(session: AsyncSession = Depends(get_session)) -> SqlConversaRepository:
    return SqlConversaRepository(session)


def get_broadcast_repo(session: AsyncSession = Depends(get_session)) -> SqlBroadcastRepository:
    return SqlBroadcastRepository(session)


def get_audit_repo(session: AsyncSession = Depends(get_session)) -> SqlAuditLogRepository:
    return SqlAuditLogRepository(session)


def get_contato_repo(session: AsyncSession = Depends(get_session)) -> SqlContatoRepository:
    return SqlContatoRepository(session)


def get_sala_repo(session: AsyncSession = Depends(get_session)) -> SqlSalaRepository:
    return SqlSalaRepository(session)


def get_aluno_repo(session: AsyncSession = Depends(get_session)) -> SqlAlunoRepository:
    return SqlAlunoRepository(session)


def get_professor_repo(session: AsyncSession = Depends(get_session)) -> SqlProfessorRepository:
    return SqlProfessorRepository(session)


def get_canal(settings: Settings = Depends(get_settings_dep)) -> MessageChannel:
    """Canal de mensagens (demo ou Meta) para envios avulsos de texto."""
    return criar_canal(settings)


def get_llm(settings: Settings = Depends(get_settings_dep)) -> LLMProvider:
    """Provedor de LLM (fake/Anthropic/OpenAI) para tarefas de normalização/extração."""
    return criar_llm(settings)


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
        tenants=SqlTenantRepository(session),
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


def get_atualizar_fonte_conhecimento(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> AtualizarFonteConhecimento:
    """Edição de um documento da base — reindexa o RAG com o texto novo."""
    return AtualizarFonteConhecimento(
        fontes=SqlFonteConhecimentoRepository(session),
        embedder=criar_embedder(settings),
        store=PgVectorStore(session),
    )


def get_definir_ativo_fonte_conhecimento(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> DefinirAtivoFonteConhecimento:
    """Interruptor de indexação (decisão A) — a alternativa da escola ao DELETE."""
    return DefinirAtivoFonteConhecimento(
        fontes=SqlFonteConhecimentoRepository(session),
        embedder=criar_embedder(settings),
        store=PgVectorStore(session),
    )


# --------------------------------------------------------------------------- #
# Respostas rápidas ("atalhos") por tenant → RAG
# --------------------------------------------------------------------------- #
def get_resposta_rapida_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlRespostaRapidaRepository:
    return SqlRespostaRapidaRepository(session)


def get_aviso_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlAvisoTemporizadoRepository:
    return SqlAvisoTemporizadoRepository(session)


def get_impressao_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlSolicitacaoImpressaoRepository:
    return SqlSolicitacaoImpressaoRepository(session)


def get_mural_repo(session: AsyncSession = Depends(get_session)) -> SqlMuralRepository:
    return SqlMuralRepository(session)


# --------------------------------------------------------------------------- #
# Onda 2 — comunicação interna, mediação pai↔professor e cota de impressão
# --------------------------------------------------------------------------- #
def get_solicitacao_interna_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlSolicitacaoInternaRepository:
    return SqlSolicitacaoInternaRepository(session)


def get_atendimento_humano_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlAtendimentoHumanoRepository:
    return SqlAtendimentoHumanoRepository(session)


def get_responder_atendimento(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> ResponderAtendimento:
    """Resposta da secretaria ao responsável, pelo número da própria escola (§6j)."""
    return ResponderAtendimento(
        atendimentos=SqlAtendimentoHumanoRepository(session),
        conversas=SqlConversaRepository(session),
        canal=criar_canal(settings),
        tenants=SqlTenantRepository(session),
        templates=SqlTemplateRepository(session),
        template_retomada=settings.template_retomada_atendimento,
    )


def get_mediacao_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlMediacaoRepository:
    return SqlMediacaoRepository(session)


def get_cota_impressao_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlCotaImpressaoRepository:
    return SqlCotaImpressaoRepository(session)


# --------------------------------------------------------------------------- #
# Onda 3 — falta/eventual (I1), ficha de matrícula (D1/D2/D3), matrícula (E1)
# --------------------------------------------------------------------------- #
def get_falta_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlAvisoFaltaRepository:
    return SqlAvisoFaltaRepository(session)


def get_ficha_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlFichaMatriculaRepository:
    return SqlFichaMatriculaRepository(session)


def get_matricula_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlSolicitacaoMatriculaRepository:
    return SqlSolicitacaoMatriculaRepository(session)
