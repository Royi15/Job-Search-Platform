"""Application configuration.

Single source of truth for environment config. Everything comes from
environment variables (or backend/.env in development) via pydantic-settings,
so misconfiguration fails fast at startup instead of deep in a request.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    debug: bool = False

    # Infrastructure
    database_url: str = "postgresql+asyncpg://jobsearch:jobsearch@localhost:5432/jobsearch"
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 14

    # LLM (platform-owned key; users never see or supply it)
    llm_api_key: str = ""
    llm_model: str = "gemini-3.1-flash-lite"
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    # Telegram bot
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_webhook_secret: str = ""

    # Discord community channel (webhook — no bot process needed)
    discord_webhook_url: str = ""

    # Bright Data — LinkedIn student-jobs discovery
    brightdata_api_key: str = ""
    brightdata_dataset_id: str = "gd_lpfll7v5hcqtkxl6l"
    brightdata_keyword: str = "student"
    brightdata_location: str = "israel"
    brightdata_country: str = "IL"
    brightdata_time_range: str = "Past 24 hours"

    # Files / CORS
    upload_dir: str = "./uploads"
    max_upload_bytes: int = 8 * 1024 * 1024
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
