"""Configuração da aplicação (carregada de variáveis de ambiente)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
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

    # Autenticação (JWT) — segredo de assinatura HS256 e validade do token (minutos).
    # Em produção, defina JWT_SECRET com um valor forte e secreto.
    jwt_secret: str = "troque-este-segredo-jwt"
    jwt_expira_minutos: int = 480  # 8 horas

    # Meta WhatsApp Cloud API
    meta_phone_number_id: str | None = None
    meta_waba_id: str | None = None
    meta_access_token: str | None = None
    meta_webhook_verify_token: str = "changeme"
    meta_daily_tier_limit: int = 1000

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
