"""Application configuration via pydantic-settings (MVP-01)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and optional .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="vb-browser-use")
    app_env: str = Field(default="dev")
    api_key: str = Field(default="")
    db_path: Path = Field(default=Path("data/app.db"))
    artifacts_dir: Path = Field(default=Path("artifacts"))
    profiles_dir: Path = Field(default=Path("profiles"))
    log_level: str = Field(default="INFO")
    log_jsonl_path: Path | None = Field(default=None)
    pii_encryption_key: str = Field(default="dev-local-pii-key-change-in-prod")
    pii_ttl_days: int = Field(default=30, ge=1)
    booking_idempotency_ttl_seconds: int = Field(default=86400, ge=60)
    max_concurrent_sessions: int = Field(default=3, ge=1)
    hitl_timeout_seconds: int = Field(default=300, ge=10)
    otp_timeout_seconds: int = Field(default=900, ge=60, le=900)
    sqlite_busy_timeout_ms: int = Field(default=5000, ge=100)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
