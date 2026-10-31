from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SUBSY_", extra="ignore")

    app_name: str = "Subsy"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://subsy:subsy@localhost:5432/subsy"
    secret_key: str = "change-me-in-production-please-use-a-long-random-string"
    access_token_minutes: int = 480
    reset_token_minutes: int = 30
    frontend_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # SMTP — when smtp_host is empty, emails are written to the outbox table only (dev fallback)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Subsy <no-reply@subsy.local>"

    # Automation
    scheduler_enabled: bool = True
    billing_cron_hour: int = 1
    renewal_reminder_days: int = 7

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
