"""Fábricas que escolhem adaptadores conforme a configuração (env).

Mantêm a seleção de provedor fora do domínio e das interfaces.
"""

from __future__ import annotations

from app.config import Settings
from app.domain.ports import (
    EmailSender,
    Embedder,
    FonteMidia,
    LLMProvider,
    MessageChannel,
)
from app.infrastructure.channel.demo_channel import DemoMessageChannel
from app.infrastructure.llm.fake_provider import FakeEmbedder, FakeLLMProvider


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
