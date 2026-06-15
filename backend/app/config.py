"""Configuração da aplicação (carregada de variáveis de ambiente)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://tiescolar:tiescolar@db:5432/tiescolar"
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
