"""Fábricas que escolhem adaptadores conforme a configuração (env).

Mantêm a seleção de provedor fora do domínio e das interfaces.
"""

from __future__ import annotations

from app.config import Settings
from app.domain.ports import EmailSender, Embedder, LLMProvider, MessageChannel
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


# Canal "demo" é mantido como singleton de processo para inspeção no demo.
_demo_channel = DemoMessageChannel()


def criar_canal(settings: Settings) -> MessageChannel:
    if settings.message_channel == "meta" and settings.meta_access_token:
        from app.infrastructure.channel.meta_channel import MetaMessageChannel

        return MetaMessageChannel(
            phone_number_id=settings.meta_phone_number_id or "",
            access_token=settings.meta_access_token,
        )
    return _demo_channel


def canal_demo() -> DemoMessageChannel:
    return _demo_channel


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
