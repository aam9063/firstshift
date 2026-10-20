"""FirstShift application settings (12-factor: configuration via environment)."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Local Postgres from docker compose (host port 5433).
    database_url: str = "postgresql+psycopg://firstshift:firstshift@localhost:5433/firstshift"
    redis_url: str = "redis://localhost:6379/0"
    openai_model: str = "gpt-4.1-mini"

    # Model port (F07 T1): scripted by default so tests and demos never touch
    # the network. LLM_MODE=live selects the Strands OpenAI provider, which
    # requires OPENAI_API_KEY.
    llm_mode: Literal["live", "scripted"] = "scripted"
    openai_api_key: str | None = None

    # Langfuse trace hook (optional): absent keys mean a no-op tracer.
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"


settings = Settings()
