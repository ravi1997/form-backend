from flask_jwt_extended import JWTManager, get_jwt
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flasgger import Swagger
from flask import request
from config.settings import settings


def tenant_aware_key_func():
    """
    Generates a rate-limit key based on Organization ID or IP address.
    Ensures that one tenant cannot exhaust API resources for another.
    """
    try:
        # Check for org ID in JWT claims first
        claims = get_jwt()
        org_id = claims.get("organization_id")
        if org_id:
            return f"tenant:{org_id}"
    except Exception:
        pass

    # Fallback to header or IP
    org_header = request.headers.get("X-Organization-ID")
    if org_header:
        return f"tenant:{org_header}"

    return get_remote_address()


jwt = JWTManager()
cors = CORS()

# Limiter uses dedicated DB (REDIS_DB_RATE_LIMITER = 3) to avoid collisions.
_redis_pass = f":{settings.REDIS_PASSWORD}@" if settings.REDIS_PASSWORD else ""
limiter_storage = (
    f"redis://{_redis_pass}{settings.REDIS_HOST}:{settings.REDIS_PORT}"
    f"/{settings.REDIS_DB_RATE_LIMITER}"
)

limiter = Limiter(
    key_func=tenant_aware_key_func,
    default_limits=["2000 per hour", "100 per minute"],
    storage_uri=limiter_storage,
)
talisman = Talisman(force_https=False)

# ── Shared Redis client (app cache DB) ───────────────────────────────────────
# Used by idempotency middleware and other modules needing a simple
# get/set/setex interface without the full RedisService overhead.
# DB allocation: settings.REDIS_DB_APP_CACHE (default 0).
try:
    import redis as _redis

    redis_client = _redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB_APP_CACHE,
        password=settings.REDIS_PASSWORD,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
except Exception:
    redis_client = None  # type: ignore[assignment]

# --- Swagger Global Configuration ---
template = {
    "swagger": "2.0",
    "info": {
        "title": "Forms Backend API",
        "description": "Comprehensive API for managing forms, responses, and AI analysis.",
        "version": "1.0.0",
    },
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": 'JWT Authorization header using the Bearer scheme. Example: "Authorization: Bearer {token}"',
        }
    },
}

# Try to load generated definitions for Flasgger
# This provides all Pydantic models as OpenAPI definitions
try:
    import json
    import os

    # Try multiple possible paths to accommodate different launch contexts
    base_path = os.path.dirname(os.path.abspath(__file__))
    def_path = os.path.join(base_path, "docs/swagger_definitions.json")
    if os.path.exists(def_path):
        with open(def_path, "r") as f:
            template["definitions"] = json.load(f)
except Exception:
    pass

swagger = Swagger(template=template)
