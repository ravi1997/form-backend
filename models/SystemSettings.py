from mongoengine import StringField, IntField, BooleanField
from models.base import BaseDocument


class SystemSettings(BaseDocument):
    """
    Singleton-style document that stores backend configuration that can be
    updated dynamically by a superadmin via the API.
    """

    meta = {
        "collection": "system_settings",
        "indexes": [
            {"fields": ["env_key"], "unique": True},
        ],
        "index_background": True,
    }

    env_key = StringField(required=True, default="default")

    # ── JWT / Auth Settings ─────────────────────────────────────────────
    jwt_access_token_expires_minutes = IntField(default=60)
    jwt_refresh_token_expires_days = IntField(default=30)
    max_failed_login_attempts = IntField(default=5)
    account_lock_duration_hours = IntField(default=24)
    password_expiration_days = IntField(default=90)
    otp_expiration_minutes = IntField(default=5)
    max_otp_resends = IntField(default=5)

    # ── File Upload Settings ─────────────────────────────────────────────
    max_upload_size_mb = IntField(default=10)
    allowed_upload_extensions = StringField(
        default="pdf,docx,xlsx,jpg,jpeg,png,gif,svg,mp4,mp3"
    )

    # ── Cache Settings ───────────────────────────────────────────────────
    cache_enabled = BooleanField(default=True)
    cache_default_ttl_seconds = IntField(default=300)
    cache_form_schema_ttl_seconds = IntField(default=3600)
    cache_user_session_ttl_seconds = IntField(default=1800)
    cache_query_result_ttl_seconds = IntField(default=300)
    cache_dashboard_widget_ttl_seconds = IntField(default=120)
    cache_api_response_ttl_seconds = IntField(default=60)

    # ── LLM / AI Settings ───────────────────────────────────────────────
    llm_provider = StringField(default="ollama")
    llm_api_url = StringField(default="http://ollama:11434/v1")
    llm_model = StringField(default="llama3")
    ollama_api_url = StringField(default="http://localhost:11434")
    ollama_embedding_model = StringField(default="nomic-embed-text")
    ollama_pool_size = IntField(default=5)
    ollama_pool_timeout_seconds = IntField(default=30)
    ollama_connection_timeout_seconds = IntField(default=10)

    # ── Redis Settings ───────────────────────────────────────────────────
    redis_host = StringField(default="localhost")
    redis_port = IntField(default=6379)
    redis_db = IntField(default=0)
    redis_max_connections = IntField(default=50)
    redis_socket_timeout_seconds = IntField(default=5)

    # ── CORS / Security ──────────────────────────────────────────────────
    cors_enabled = BooleanField(default=True)
    debug_mode = BooleanField(default=False)
    rate_limit_enabled = BooleanField(default=True)
    rate_limit_requests_per_minute = IntField(default=100)

    updated_by = StringField()

    @classmethod
    def get_or_create_default(cls):
        """Return the singleton settings doc, creating it if absent."""
        doc = cls.objects(env_key="default").first()
        if not doc:
            doc = cls(env_key="default")
            doc.save()
        return doc

    def to_dict(self):
        # Exclude internal fields from dict representation if needed
        data = self.to_mongo().to_dict()
        if "_id" in data:
            data["id"] = str(data.pop("_id"))
        return data
