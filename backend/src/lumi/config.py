"""Typed application settings loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split_csv(value: object) -> object:
    """Parse comma-separated env strings into lists."""
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


def _split_csv_int(value: object) -> object:
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):
        return [int(item.strip()) for item in value.split(",") if item.strip()]
    return value


CsvStrList = Annotated[list[str], NoDecode, BeforeValidator(_split_csv)]
CsvIntList = Annotated[list[int], NoDecode, BeforeValidator(_split_csv_int)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ---
    app_env: str = "local"
    app_name: str = "Lumi"
    app_public_url: str | None = None
    backend_base_url: str = "http://localhost:8000"
    frontend_public_path: str = "/app"
    default_timezone: str = "Europe/Moscow"
    app_secret_key: str = "change-me-local-secret"
    encryption_key: str = "change-me-fernet-key"

    # --- Database / Redis ---
    database_url: str = "postgresql+asyncpg://lumi:lumi@localhost:5432/lumi"
    redis_url: str = "redis://localhost:6379/0"

    # --- Telegram ---
    telegram_bot_token: str = ""
    allowed_telegram_user_ids: CsvIntList = Field(default_factory=list)
    log_unauthorized_telegram_ids: bool = True
    telegram_image_max_bytes: int = 10_000_000
    telegram_webhook_enabled: bool = False
    telegram_webhook_secret: str | None = None
    telegram_chat_debounce_ms: int = 1200
    telegram_turn_lock_seconds: int = 300
    telegram_turn_max_retries: int = 3
    telegram_turn_retry_base_seconds: int = 10
    telegram_max_queue_per_user: int = 25
    telegram_use_rich_messages: bool = False
    telegram_stream_final_replies: bool = True
    telegram_stream_edit_interval_seconds: float = 1.15
    telegram_stream_min_chars: int = 48
    telegram_stream_max_chars: int = 3900

    # --- Worker ---
    worker_max_jobs: int = 10

    # --- LLM ---
    llm_provider: Literal["minimax", "mock"] = "mock"
    minimax_api_key: str | None = None
    minimax_base_url: str = "https://api.minimax.io/v1"
    minimax_model: str = "MiniMax-M3"
    llm_timeout_seconds: int = 90
    llm_max_retries: int = 3
    llm_context_max_chars: int = 120_000
    store_llm_debug_payloads: bool = False

    # --- Context / compaction ---
    recent_messages_limit: int = 30
    compact_after_messages: int = 80
    compact_after_chars: int = 160_000
    summary_target_chars: int = 12_000

    # --- Google connector ---
    google_oauth_client_secret_file: str | None = "/app/data/secrets/google_client_secret.json"
    google_oauth_token_file: str | None = "/app/data/secrets/google_token.json"
    google_scopes: CsvStrList = Field(
        default_factory=lambda: [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events",
        ]
    )
    calendar_sync_days_ahead: int = 90
    calendar_sync_days_back: int = 1
    store_email_bodies: bool = False

    # --- News ---
    news_default_topics: CsvStrList = Field(
        default_factory=lambda: ["AI agents", "Telegram Mini Apps", "LLM pricing"]
    )
    news_max_items_per_topic: int = 10

    # --- Scheduler ---
    scheduler_tick_seconds: int = 30
    scheduler_lock_seconds: int = 300

    # --- Local dev only ---
    dev_auth_enabled: bool = False
    dev_auth_telegram_user_id: int | None = None
    auto_migrate: bool = False

    @field_validator(
        "app_public_url",
        "minimax_api_key",
        "telegram_webhook_secret",
        "google_oauth_client_secret_file",
        "google_oauth_token_file",
        "dev_auth_telegram_user_id",
        mode="before",
    )
    @classmethod
    def _empty_env_is_none(cls, value: object) -> object:
        """Blank values in .env (`KEY=`) mean 'not set' for optional fields."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"

    @property
    def llm_configured(self) -> bool:
        return self.llm_provider == "mock" or bool(self.minimax_api_key)

    @property
    def mini_app_url(self) -> str | None:
        if not self.app_public_url:
            return None
        return self.app_public_url.rstrip("/") + self.frontend_public_path


@lru_cache
def get_settings() -> Settings:
    return Settings()
