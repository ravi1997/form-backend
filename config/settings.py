"""
config/settings.py
Centralised application configuration using pydantic-settings.
Values are loaded from environment variables and optionally a .env file.
"""

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # ── App ─────────────────────────────────────────────────────────────────
    APP_NAME: str = "Forms Backend"
    APP_ENV: str = "development"
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE: int = 200

    @property
    def DEBUG(self) -> bool:
        return self.APP_ENV == "development"

    # ── MongoDB ──────────────────────────────────────────────────────────────
    MONGODB_URI: str = "mongodb://localhost:27017/forms_db"

    # ── Redis ────────────────────────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    CACHE_ENABLED: bool = True
    RESPONSE_CACHE_TTL: int = 3600  # 1 hour default

    # ── Celery ───────────────────────────────────────────────────────────────
    CELERY_BROKER_DB: int = 0
    CELERY_RESULT_DB: int = 1

    # ── Security ──────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "super-secret-key-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    FIELD_ENCRYPTION_KEY: Optional[str] = None

    # ── Sentry ───────────────────────────────────────────────────────────────
    SENTRY_DSN: Optional[str] = None
    SENTRY_TRACES_SAMPLE_RATE: float = Field(default=0.1, ge=0.0, le=1.0)
    SENTRY_PROFILES_SAMPLE_RATE: float = Field(default=0.1, ge=0.0, le=1.0)

    # ── Elasticsearch ────────────────────────────────────────────────────────
    ELASTICSEARCH_URL: str = "http://localhost:9200"

    # ── AI Providers ─────────────────────────────────────────────────────────
    AI_PROVIDER: str = "local"  # "local", "ollama", "openai"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OPENAI_API_KEY: Optional[str] = None
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # ── OLAP & Analytics ─────────────────────────────────────────────────────
    OLAP_ENGINE: str = "duckdb"  # "duckdb", "clickhouse"
    DUCKDB_PATH: str = "analytics.duckdb"
    CLICKHOUSE_URL: Optional[str] = None

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore",
    }

    @model_validator(mode="after")
    def validate_secrets(self) -> "Settings":
        """
        Refuse to start in production/staging with default insecure credentials.
        """
        insecure_key = "super-secret-key-change-me"
        
        if self.APP_ENV != "development":
            if self.JWT_SECRET_KEY == insecure_key:
                raise ValueError(
                    f"JWT_SECRET_KEY must be changed for {self.APP_ENV} environment. "
                    'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
                )
            
            # Enforce non-local infrastructure for production
            if "localhost" in self.MONGODB_URI or "127.0.0.1" in self.MONGODB_URI:
                raise ValueError("MONGODB_URI must not point to localhost in non-development environments.")
            
            if "localhost" in self.REDIS_HOST or "127.0.0.1" in self.REDIS_HOST:
                raise ValueError("REDIS_HOST must not point to localhost in non-development environments.")
                
        return self


settings = Settings()
