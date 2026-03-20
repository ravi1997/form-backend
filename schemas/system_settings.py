from typing import Optional
from .base import BaseSchema


class SystemSettingsSchema(BaseSchema):
    env_key: str = "default"

    # Auth Settings
    jwt_access_token_expires_minutes: int = 60
    jwt_refresh_token_expires_days: int = 30
    max_failed_login_attempts: int = 5
    account_lock_duration_hours: int = 24
    password_expiration_days: int = 90
    otp_expiration_minutes: int = 5
    max_otp_resends: int = 5

    # File Upload
    max_upload_size_mb: int = 10
    allowed_upload_extensions: str = "pdf,docx,xlsx,jpg,jpeg,png,gif,svg,mp4,mp3"

    # Cache
    cache_enabled: bool = True
    cache_default_ttl_seconds: int = 300
    cache_form_schema_ttl_seconds: int = 3600
    cache_user_session_ttl_seconds: int = 1800
    cache_query_result_ttl_seconds: int = 300
    cache_dashboard_widget_ttl_seconds: int = 120
    cache_api_response_ttl_seconds: int = 60

    # LLM Settings
    llm_provider: str = "ollama"
    llm_api_url: str = "http://ollama:11434/v1"
    llm_model: str = "llama3"
    ollama_api_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_pool_size: int = 5
    ollama_pool_timeout_seconds: int = 30
    ollama_connection_timeout_seconds: int = 10

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_max_connections: int = 50
    redis_socket_timeout_seconds: int = 5

    # Security Layer
    cors_enabled: bool = True
    debug_mode: bool = False
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 100

    updated_by: Optional[str] = None
