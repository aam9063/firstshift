"""FirstShift application settings (12-factor: configuration via environment)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Local Postgres from docker compose (host port 5433).
    database_url: str = "postgresql+psycopg://firstshift:firstshift@localhost:5433/firstshift"
    redis_url: str = "redis://localhost:6379/0"
    openai_model: str = "gpt-4.1-mini"


settings = Settings()
