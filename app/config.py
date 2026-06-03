# app/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Literal


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    pydantic-settings automatically reads from .env file and
    environment variables, with env vars taking precedence.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application ──────────────────────────────────────────
    APP_NAME: str = "URL Shortener"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "testing", "production"] = "development"
    DEBUG: bool = False
    BASE_URL: str = "http://localhost:8000"  # Used when building full short URLs

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str  # Required — no default, must be set
    # For async SQLAlchemy, we need postgresql+asyncpg://
    # The property below ensures the right driver prefix

    # ── Short Code Config ─────────────────────────────────────
    SHORT_CODE_LENGTH: int = 7
    SHORT_CODE_MAX_RETRIES: int = 3

    # ── Rate Limiting ─────────────────────────────────────────
    RATE_LIMIT_REQUESTS: int = 60   # requests
    RATE_LIMIT_WINDOW: int = 60     # seconds

    # ── Link Defaults ─────────────────────────────────────────
    DEFAULT_EXPIRY_DAYS: int | None = None  # None = never expires

    @property
    def async_database_url(self) -> str:
        """
        Ensure the database URL uses the asyncpg driver.
        Converts postgresql:// or postgres:// to postgresql+asyncpg://
        This lets us use a standard DATABASE_URL in .env but get
        the async driver automatically.
        """
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        if "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_testing(self) -> bool:
        return self.ENVIRONMENT == "testing"


@lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.
    
    @lru_cache means this is only instantiated once per process —
    not once per request. This is important for performance and
    also means settings are effectively immutable at runtime.
    
    To override in tests: use FastAPI's dependency_overrides.
    """
    return Settings()