"""Global application settings powered by Pydantic v2."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application configuration loaded from .env / environment."""

    # ---- LLM / Embeddings ----
    openai_api_key: str = Field(default="sk-placeholder", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        alias="EMBEDDING_MODEL",
    )

    # ---- Data sources ----
    polygon_api_key: str | None = Field(default=None, alias="POLYGON_API_KEY")
    alpha_vantage_key: str | None = Field(default=None, alias="ALPHA_VANTAGE_KEY")
    tushare_token: str | None = Field(default=None, alias="TUSHARE_TOKEN")
    coingecko_api_key: str | None = Field(default=None, alias="COINGECKO_API_KEY")

    # ---- Storage ----
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/investment.db", alias="DATABASE_URL"
    )
    chroma_persist_dir: str = Field(
        default="./data/chroma", alias="CHROMA_PERSIST_DIR"
    )

    # ---- API ----
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_env: Literal["development", "production", "test"] = Field(
        default="production", alias="APP_ENV"
    )
    secret_key: str = Field(default="change_me", alias="SECRET_KEY")
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")

    # ---- Telegram ----
    telegram_token: str | None = Field(default=None, alias="TELEGRAM_TOKEN")
    telegram_chat_id: str | None = Field(default=None, alias="TELEGRAM_CHAT_ID")

    # ---- Email ----
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    email_from: str | None = Field(default=None, alias="EMAIL_FROM")
    email_to: str | None = Field(default=None, alias="EMAIL_TO")

    # ---- Scheduler ----
    daily_report_cron: str = Field(default="0 9 * * 1-5", alias="DAILY_REPORT_CRON")
    watchlist: str = Field(default="AAPL,MSFT,TSLA", alias="WATCHLIST")

    # ---- Misc ----
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    rate_limit_per_minute: int = Field(default=30, alias="RATE_LIMIT_PER_MINUTE")
    language: Literal["zh-CN", "en-US"] = Field(default="zh-CN", alias="LANGUAGE")

    # ---- Storage cleanup ----
    # All deletions go through services.storage_cleaner with these knobs.
    # The cleaner never blocks waiting on permission prompts and silently
    # defers any file it cannot remove to the next sweep.
    cleanup_enabled: bool = Field(default=True, alias="CLEANUP_ENABLED")
    cleanup_retention_days: float = Field(default=14.0, alias="CLEANUP_RETENTION_DAYS")
    cleanup_op_timeout_seconds: float = Field(
        default=5.0, alias="CLEANUP_OP_TIMEOUT_SECONDS"
    )
    cleanup_cron: str = Field(default="30 3 * * *", alias="CLEANUP_CRON")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Resolve project paths
    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def watchlist_symbols(self) -> List[str]:
        return [s.strip() for s in self.watchlist.split(",") if s.strip()]

    @property
    def cors_origins_list(self) -> List[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, v: str) -> str:
        return v.upper()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


settings = get_settings()
