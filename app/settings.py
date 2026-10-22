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

    # Twilio WhatsApp channel (sandbox subaccount, twilio-channel T2/S2):
    # TWILIO_ACCOUNT_SID is the subaccount SID, the API key (SID + secret)
    # signs REST sends and the subaccount auth token validates inbound
    # webhook signatures. Credits draw from the parent account.
    twilio_account_sid: str | None = None
    twilio_api_key_sid: str | None = None
    twilio_api_key_secret: str | None = None
    twilio_auth_token: str | None = None
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    # None means the default: validation is on whenever an auth token is
    # present, so the inbound path is never accidentally open (S5).
    twilio_validate_signature: bool | None = None

    @property
    def require_twilio_signature(self) -> bool:
        """Whether POST /webhooks/whatsapp must validate X-Twilio-Signature."""
        if self.twilio_validate_signature is None:
            return self.twilio_auth_token is not None
        return self.twilio_validate_signature


settings = Settings()
