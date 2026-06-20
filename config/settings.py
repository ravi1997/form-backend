"""
config/settings.py
Centralised application configuration using pydantic-settings.
Values are loaded from environment variables and optionally a .env file.
"""

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings
from typing import Optional
import secrets


class Settings(BaseSettings):
    # ── App ─────────────────────────────────────────────────────────────────
    APP_NAME: str = "Forms Backend"
    APP_ENV: str = "development"
    PLATFORM_VERSION: str = "1.0.0"
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

    # ── Redis DB allocation (canonical — do not use raw integers elsewhere) ──
    # DB 0 — Application cache (idempotency, shared redis_client in extensions)
    # DB 1 — Celery task results
    # DB 2 — Analytics cache (AnalyticsCache service)
    # DB 3 — Rate limiter (Flask-Limiter storage)
    # DB 4 — Celery broker (task queue)
    REDIS_DB_APP_CACHE: int = 0
    REDIS_DB_CELERY_RESULTS: int = 1
    REDIS_DB_ANALYTICS_CACHE: int = 2
    REDIS_DB_RATE_LIMITER: int = 3
    REDIS_DB_CELERY_BROKER: int = 4

    # ── Celery ───────────────────────────────────────────────────────────────
    # These use the canonical DB constants above. DB 4 for broker avoids
    # collision with app cache (DB 0) that was present in older versions.
    @property
    def CELERY_BROKER_DB(self) -> int:
        return self.REDIS_DB_CELERY_BROKER

    @property
    def CELERY_RESULT_DB(self) -> int:
        return self.REDIS_DB_CELERY_RESULTS

    # ── Security ──────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    FIELD_ENCRYPTION_KEY: Optional[str] = None

    ALLOWED_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:8051",
            "http://localhost:8989",
            "http://localhost:9600",
        ]
    )

    # Request size limits (prevents DoS attacks)
    MAX_CONTENT_LENGTH: int = Field(
        default=16 * 1024 * 1024,  # 16MB
        description="Maximum request body size in bytes",
    )
    MAX_FILE_SIZE_FORM: int = Field(
        default=10 * 1024 * 1024,  # 10MB
        description="Maximum file upload size for forms (images, documents)",
    )
    MAX_FILE_SIZE_EXPORT: int = Field(
        default=50 * 1024 * 1024,  # 50MB
        description="Maximum file size for exports",
    )

    # Password policy (NIST SP 800-63B compliant)
    PASSWORD_MIN_LENGTH: int = Field(default=12, ge=8, le=128)
    PASSWORD_MAX_LENGTH: int = Field(default=128, ge=12, le=256)
    PASSWORD_REQUIRE_UPPERCASE: bool = Field(default=True)
    PASSWORD_REQUIRE_LOWERCASE: bool = Field(default=True)
    PASSWORD_REQUIRE_DIGITS: bool = Field(default=True)
    PASSWORD_REQUIRE_SPECIAL: bool = Field(default=True)
    PASSWORD_EXPIRATION_DAYS: int = Field(default=90, ge=30, le=365)
    PASSWORD_HISTORY_COUNT: int = Field(default=5, ge=0, le=20)
    PREVENT_COMMON_PASSWORDS: bool = Field(default=True)

    # Rate limiting
    RATE_LIMIT_LOGIN_ATTEMPTS: str = Field(default="5 per minute")
    RATE_LIMIT_PASSWORD_CHANGE: str = Field(default="3 per hour")
    RATE_LIMIT_FILE_UPLOAD: str = Field(default="10 per minute")
    RATE_LIMIT_EXPORT: str = Field(default="5 per hour")
    RATE_LIMIT_OTP_REQUEST: str = Field(default="5 per minute")

    # Export limits
    MAX_EXPORT_RECORDS: int = Field(default=10000, ge=1000, le=100000)
    REQUIRE_EXPORT_CONSENT: bool = Field(default=True)
    EXPORT_TTL_HOURS: int = Field(default=168, ge=1, le=24 * 30)
    EXPORT_STORAGE_ROOT: str = Field(default="/tmp/analysis_exports")
    EXPORT_STORAGE_BACKEND: str = Field(default="local")

    # Security headers
    HSTS_MAX_AGE: int = Field(default=0, ge=0)  # Disabled for development
    HSTS_INCLUDE_SUBDOMAINS: bool = Field(default=False)  # Disabled for development
    HSTS_PRELOAD: bool = Field(default=False)  # Disabled for development

    # Content Security Policy (even for REST APIs)
    CSP_POLICY: dict = Field(
        default_factory=lambda: {
            "default-src": ["'self'"],
            "script-src": ["'self'"],
            "object-src": ["'none'"],
        },
        description="Content-Security-Policy header configuration",
    )

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
    CLICKHOUSE_URL: Optional[str] = "http://clickhouse:8123"

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

        if not self.JWT_SECRET_KEY:
            if self.APP_ENV == "development":
                self.JWT_SECRET_KEY = secrets.token_hex(32)
            else:
                raise ValueError(
                    "JWT_SECRET_KEY must be provided via environment in non-development environments."
                )

        if self.APP_ENV != "development":
            if self.JWT_SECRET_KEY == insecure_key:
                raise ValueError(
                    f"JWT_SECRET_KEY must be changed for {self.APP_ENV} environment. "
                    'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
                )

            # Enforce non-local infrastructure for production
            if "localhost" in self.MONGODB_URI or "127.0.0.1" in self.MONGODB_URI:
                raise ValueError(
                    "MONGODB_URI must not point to localhost in non-development environments."
                )

            if "localhost" in self.REDIS_HOST or "127.0.0.1" in self.REDIS_HOST:
                raise ValueError(
                    "REDIS_HOST must not point to localhost in non-development environments."
                )

        return self


settings = Settings()
