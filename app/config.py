"""Configuração central da aplicação."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração carregada do ambiente, sem expor segredos nos logs."""

    app_name: str = "SARA 2.0"
    environment: Literal["local", "test", "production"] = "local"
    database_url: str = "postgresql+asyncpg://sara:sara@localhost:5432/sara"
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
    allowed_chat_id: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    timezone: str = Field(default="America/Sao_Paulo", min_length=1)

    model_config = SettingsConfigDict(
        env_file=(".env.local", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna a configuração da aplicação para o processo atual."""

    return Settings()
