"""Application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DEMO_MODE: bool = True
    ENV: str = "dev"

    DATABASE_URL: str = "postgresql://relay:relay@localhost:5542/relay"

    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    ANTHROPIC_API_KEY: str = ""
    MODEL_REPLY: str = "claude-haiku-4-5-20251001"

    RATE_LIMIT_PER_SECOND: int = 10
    QUIET_HOURS_START: int = 21
    QUIET_HOURS_END: int = 9
    TIMEZONE: str = "Australia/Melbourne"

    HANDOFF_WEBHOOK_URL: str = ""
    PUBLIC_BASE_URL: str = "http://localhost:8000"


settings = Settings()
