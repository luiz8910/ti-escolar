"""Fábricas que escolhem adaptadores conforme a configuração (env).

Mantêm a seleção de provedor fora do domínio e das interfaces.
"""

from __future__ import annotations

from app.config import Settings
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ports import (
    ArquivoStorage,
    CatalogoTemplates,
    EmailSender,
    Embedder,
    FonteMidia,
    LeitorDocumento,
    LLMProvider,
    MessageChannel,
)
from app.infrastructure.channel.demo_channel import DemoMessageChannel
from app.infrastructure.llm.fake_provider import FakeEmbedder, FakeLLMProvider
from app.infrastructure.llm.leitor_documento import LeitorDocumentoFake


def criar_llm(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        from app.infrastructure.llm.anthropic_provider import AnthropicLLMProvider

        return AnthropicLLMProvider(
            api_key=settings.anthropic_api_key, model=settings.llm_model
        )
    if settings.llm_provider in ("openai", "openai_compatible") and settings.openai_api_key:
        from app.infrastructure.llm.openai_provider import OpenAICompatibleLLMProvider

        return OpenAICompatibleLLMProvider(
            api_key=settings.openai_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
        )
    # "fake" (padrão) e fallback.
    return FakeLLMProvider()


def criar_leitor_documento(settings: Settings) -> LeitorDocumento:
    """Leitura de documento por IA (§4.3).

    Só a Anthropic tem adaptador: o bloco de imagem/PDF é específico da API dela, e
    escrever um segundo às cegas repetiria o erro do object storage — ir para produção sem
    nunca ter lido um arquivo de verdade. Sem chave, cai no fake, que mantém o fluxo de
    revisão demonstrável.
    """
    if settings.anthropic_api_key:
        from app.infrastructure.llm.leitor_documento import AnthropicLeitorDocumento

        return AnthropicLeitorDocumento(
            api_key=settings.anthropic_api_key, model=settings.llm_model
        )
    return LeitorDocumentoFake()


def criar_embedder(settings: Settings) -> Embedder:
    if (
        settings.embeddings_provider in ("openai", "openai_compatible")
        and settings.embeddings_api_key
    ):
        from app.infrastructure.llm.openai_provider import OpenAICompatibleEmbedder

        return OpenAICompatibleEmbedder(
            api_key=settings.embeddings_api_key,
            model=settings.embeddings_model,
            dimensao=settings.embedding_dim,
            base_url=settings.embeddings_base_url,
        )
    # Fake determinístico (sem rede/chaves).
    return FakeEmbedder(dimensao=settings.embedding_dim)


# Singleton de processo: sem o demo Next.js, este canal é apenas o **fallback** de
# ``criar_canal`` — o que sobra quando ``MESSAGE_CHANNEL=meta`` está sem token. Mantê-lo
# como um objeto só evita perder os envios de uma instância a cada requisição, o que é o
# que ``canal_efetivo`` precisa poder acusar.
_demo_channel = DemoMessageChannel()


def canal_efetivo(settings: Settings) -> str:
    """Qual adaptador ``criar_canal`` devolve **de fato** — nem sempre o da env.

    ``MESSAGE_CHANNEL=meta`` sem ``META_ACCESS_TOKEN`` cai no canal demo sem erro nenhum, e
    esse é o estado mais perigoso do go-live: o inbound é roteado, chama a LLM (custo real) e
    marca o atendimento como concluído, mas a resposta sai pelo demo e nunca chega ao
    responsável — sem nada aparecer como falha. Reportar a env em vez do adaptador real
    esconde exatamente esse caso, então quem quiser exibir o canal usa esta função.
    """
    if settings.message_channel == "meta" and settings.meta_access_token:
        return "meta"
    return "demo"


def criar_canal(settings: Settings) -> MessageChannel:
    if canal_efetivo(settings) == "meta":
        from app.infrastructure.channel.meta_channel import MetaMessageChannel

        return MetaMessageChannel(
            phone_number_id=settings.meta_phone_number_id or "",
            access_token=settings.meta_access_token or "",
        )
    return _demo_channel


def storage_efetivo(settings: Settings) -> str:
    """Qual adaptador ``criar_arquivo_storage`` devolve **de fato** — nem sempre o da env.

    Espelha o ``canal_efetivo`` acima, e pela mesma lição: ``MESSAGE_CHANNEL=meta`` sem token
    caía no demo **sem erro nenhum**, e o WhatsApp simplesmente não estava no ar. Um
    ``ARQUIVO_STORAGE=s3`` sem bucket ou sem credencial que caísse no Postgres em silêncio
    repetiria a falha — só que com atestado médico de criança indo para o banco errado, e
    inflando um banco cobrado por GB sem ninguém notar.

    Credencial vazia **não** é motivo para reprovar: em EC2/ECS o boto3 pega a role da
    instância, e exigir chave explícita quebraria o caminho mais seguro. O que se exige é o
    bucket, sem o qual não há para onde escrever.
    """
    if settings.arquivo_storage == "s3" and settings.s3_bucket_documentos:
        return "s3"
    return "postgres"


def criar_arquivo_storage(settings: Settings, session: AsyncSession) -> ArquivoStorage:
    """O storage dos bytes dos arquivos recebidos (§6k).

    Recebe a sessão porque o adaptador Postgres precisa dela — é o que lhe dá a
    atomicidade entre bytes e metadado. O adaptador S3 a ignora, e essa assimetria é o
    próprio ponto da §0.3: com o S3 a transação deixa de cobrir os dois.
    """
    if storage_efetivo(settings) == "s3":
        from app.infrastructure.storage_s3 import S3ArquivoStorage

        return S3ArquivoStorage(
            bucket=settings.s3_bucket_documentos,
            region=settings.aws_region,
            access_key=settings.aws_access_key_id or "",
            secret_key=settings.aws_secret_access_key or "",
            endpoint_url=settings.s3_endpoint_url,
            kms_key_id=settings.s3_kms_key_id,
        )
    from app.infrastructure.storage import PostgresArquivoStorage

    return PostgresArquivoStorage(session)


def criar_fonte_midia(settings: Settings) -> FonteMidia:
    """Adaptador de download de mídia, alinhado ao canal **efetivo** (§9c).

    Amarrado a ``canal_efetivo`` e não a ``MESSAGE_CHANNEL`` pelo mesmo motivo do canal:
    ``meta`` sem token cai no demo, e um baixador que tentasse falar com a Graph API sem
    credencial só produziria erro repetido a cada foto que um pai enviasse.
    """
    if canal_efetivo(settings) == "meta":
        from app.infrastructure.channel.meta_midia import MetaFonteMidia

        return MetaFonteMidia(access_token=settings.meta_access_token or "")
    from app.infrastructure.channel.meta_midia import FonteMidiaIndisponivel

    return FonteMidiaIndisponivel()


def criar_catalogo_templates(settings: Settings) -> CatalogoTemplates:
    """Adaptador de gestão de templates, alinhado ao canal **efetivo** (§9c).

    Precisa de uma coisa que o envio não precisa: o escopo
    ``whatsapp_business_management`` no token. Isso só aparece na primeira chamada — o que
    dá para decidir aqui é apenas se existe token.

    **Qual conta usar não é decisão daqui.** Até 13/ago/2026 era: o adaptador nascia
    amarrado à ``META_WABA_ID``, e com isso todo template ia para a mesma conta,
    independentemente de onde estivesse o número da escola. A conta agora vem do banco
    (`Waba`), por escola, e é parâmetro de cada chamada.
    """
    if canal_efetivo(settings) != "meta":
        from app.infrastructure.channel.meta_templates import CatalogoTemplatesAusente

        return CatalogoTemplatesAusente(
            "O canal do WhatsApp está em modo demo — configure MESSAGE_CHANNEL=meta e "
            "META_ACCESS_TOKEN para gerenciar templates na Meta."
        )
    from app.infrastructure.channel.meta_templates import MetaCatalogoTemplates

    return MetaCatalogoTemplates(access_token=settings.meta_access_token or "")


def criar_email_sender(settings: Settings) -> EmailSender:
    """Escolhe o adaptador de e-mail por ``EMAIL_PROVIDER`` (``log`` | ``resend``).

    Sem chave configurada, cai no adaptador de log em vez de falhar: um deploy sem
    RESEND_API_KEY não deve derrubar a aplicação inteira por causa do aviso de licença —
    mas o painel de segurança sinaliza a situação, para não passar despercebida.
    """
    if settings.email_provider == "resend" and settings.resend_api_key:
        from app.infrastructure.messaging.email import ResendEmailSender

        return ResendEmailSender(
            remetente=settings.email_from, api_key=settings.resend_api_key
        )
    from app.infrastructure.messaging.email import LogEmailSender

    return LogEmailSender(remetente=settings.email_from)
