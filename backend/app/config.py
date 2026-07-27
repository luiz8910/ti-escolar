"""Configuração da aplicação (carregada de variáveis de ambiente)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://tiescolar:tiescolar@db:5432/tiescolar"

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalizar_dsn(cls, valor: str) -> str:
        """Aceita o DSN cru do Render/Heroku (``postgres://``/``postgresql://``) e força
        o driver psycopg v3 (async) exigido pelo SQLAlchemy desta aplicação."""
        if not isinstance(valor, str):
            return valor
        if valor.startswith("postgres://"):
            valor = "postgresql://" + valor[len("postgres://") :]
        if valor.startswith("postgresql://"):
            valor = "postgresql+psycopg://" + valor[len("postgresql://") :]
        return valor
    backend_cors_origins: str = "http://localhost:3000"

    # LLM — "fake" | "anthropic" | "openai" | "openai_compatible"
    llm_provider: str = "fake"
    llm_model: str = "claude-opus-4-8"
    llm_base_url: str = "https://api.openai.com/v1"  # usado por openai/openai_compatible
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Embeddings — "fake" | "openai" | "openai_compatible"
    embedding_dim: int = 1536  # dimensão da coluna pgvector (text-embedding-3-small = 1536)
    embeddings_provider: str = "fake"
    embeddings_base_url: str = "https://api.openai.com/v1"
    embeddings_api_key: str | None = None
    embeddings_model: str = "text-embedding-3-small"

    # Canal
    message_channel: str = "demo"

    # Super admin (criado no seed)
    super_admin_email: str = "admin@tiescolar.test"
    super_admin_senha: str = "troque-esta-senha"
    super_admin_nome: str = "Super Admin"

    # Admin do tenant demo (criado no seed)
    demo_admin_email: str = "admin@escola-demo.test"
    demo_admin_senha: str = "escola123"
    # Senha do professor demo (login do mural do professor — §A1)
    demo_professor_senha: str = "prof123"

    # Autenticação (JWT) — segredo de assinatura HS256 e validade do token (minutos).
    # Em produção, defina JWT_SECRET com um valor forte e secreto.
    jwt_secret: str = "troque-este-segredo-jwt"
    jwt_expira_minutos: int = 480  # 8 horas

    # Inbound / UX das mensagens dos pais (§G1)
    # Limite de caracteres da mensagem do responsável; acima disso o bot pede objetividade
    # sem acionar a LLM. 0 desativa o limite.
    mensagem_pai_max_chars: int = 1000

    # Licenciamento / avisos por e-mail
    # Janela (em dias) para avisar que a licença anual está perto de vencer.
    license_warning_days: int = 30
    # Remetente dos e-mails administrativos (adaptador atual é mock/log).
    email_from: str = "no-reply@tiescolar.test"

    # Meta WhatsApp Cloud API
    # Número remetente PADRÃO (fallback): usado quando a escola não tem o seu próprio
    # phone_number_id cadastrado. Em produção multi-tenant cada escola tem o seu — ver §9e.
    meta_phone_number_id: str | None = None
    meta_waba_id: str | None = None
    # Token de USUÁRIO DO SISTEMA (o token da tela de Configuração da API expira em 24h).
    meta_access_token: str | None = None
    # Token do handshake GET do webhook (hub.verify_token). TROQUE em produção.
    meta_webhook_verify_token: str = "changeme"
    meta_daily_tier_limit: int = 1000
    # App secret usado para validar a assinatura X-Hub-Signature-256 dos webhooks.
    meta_app_secret: str | None = None
    # Valida a assinatura dos webhooks da Meta. OBRIGATÓRIO em produção: sem isso o
    # endpoint aceita qualquer POST, permitindo forjar status de entrega e mensagens.
    meta_validate_signature: bool = False

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
