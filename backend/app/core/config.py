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
    llm_model: str = "gemini-3.5-flash-lite"
    # Used for calls that attach inline audio — verify this model actually
    # accepts audio input; override via env if the default doesn't.
    llm_audio_model: str = "gemini-3.5-flash-lite"
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    # Telegram bot
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_webhook_secret: str = ""

    # Discord community channel (webhook — no bot process needed)
    discord_webhook_url: str = ""

    # Bright Data — LinkedIn student-jobs discovery
    # Defaults to on so the VM needs no .env change to keep working as-is.
    # Set to false in a LOCAL backend/.env so a developer running the worker
    # locally for other features (notebooks/quizzes/interview) doesn't also
    # fire a real hourly scrape against the shared production Bright Data
    # key — two workers (local + VM) both polling independently is exactly
    # what caused duplicate job notifications in production. fetch_and_notify
    # stays manually triggerable via `python -m scripts.trigger_fetch`
    # regardless of this flag, for testing the job-search path on demand.
    enable_job_scraping_cron: bool = True
    brightdata_api_key: str = ""
    brightdata_dataset_id: str = "gd_lpfll7v5hcqtkxl6l"
    brightdata_keyword: str = "student"
    brightdata_location: str = "israel"
    brightdata_country: str = "IL"
    brightdata_time_range: str = "Past 24 hours"
    # Filters at the source (LinkedIn's own seniority field on each posting)
    # instead of guessing relevance from keywords after the fact — a senior
    # role that happens to mention "students" in its description would pass
    # a text filter but not this. Matches this platform's actual audience
    # (README: "students and junior engineers"); Associate-and-above are
    # deliberately excluded as not "junior" enough.
    brightdata_experience_level: list[str] = ["Internship", "Entry level"]

    # Files / CORS
    upload_dir: str = "./uploads"
    max_upload_bytes: int = 8 * 1024 * 1024
    # PDF/PPTX notebook sources go through Gemini inline, capped at Google's
    # own inline-request ceiling (~20MB).
    max_notebook_upload_bytes: int = 20 * 1024 * 1024
    # MP3 sources go through the Files API (llm.upload_file) instead, which
    # has a much higher ceiling — sized for real lecture-length recordings.
    max_notebook_audio_bytes: int = 150 * 1024 * 1024
    cors_origins: list[str] = ["http://localhost:5173"]

    # Trivisum runs against the platform's own Gemini key — a cap on how
    # many quizzes a user can have AT ONCE (deleting frees up a slot,
    # explicitly chosen over a harder-to-game lifetime counter for
    # friendlier UX). "Generate more" on an existing quiz doesn't count
    # against this; it has its own separate 100-questions-per-quiz cap
    # instead. Easy to raise later; starting conservative since this is a
    # new, unmeasured cost.
    quiz_generation_limit: int = 30
    # Same reasoning and pattern as quiz_generation_limit (max AT ONCE, not
    # lifetime — deleting frees a slot) — notebooks share the same
    # platform-owned key, and an MP3 notebook (Files API + up to 65536
    # output tokens + a 420s generation call) is actually the single most
    # expensive generation path in the app, more so than a quiz. Kept as
    # its own separate value so the two can be tuned independently.
    notebook_generation_limit: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
