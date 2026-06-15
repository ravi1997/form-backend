from datetime import datetime, timezone
from functools import wraps

from flask import g, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from logger.unified_logger import app_logger
from services.api_key_service import ApiKeyService
from utils.response_helper import error_response


def require_api_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        raw_key = request.headers.get("X-API-Key")
        if not raw_key:
            return error_response("X-API-Key header is required", 401)

        key = ApiKeyService.get_active_key(raw_key)
        if key is None:
            app_logger.warning("API key auth failed for path %s", request.path)
            return error_response("Invalid or expired API key", 403)

        if not ApiKeyService.rate_limit_key(raw_key):
            return error_response("API key rate limit exceeded", 429)

        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = key.last_used_at or None
        key.last_used_at = datetime.now(timezone.utc)
        key.save()
        return fn(*args, **kwargs)

    return wrapper


def require_api_key_or_jwt(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        raw_key = request.headers.get("X-API-Key")
        if raw_key:
            key = ApiKeyService.get_active_key(raw_key)
            if key is None:
                app_logger.warning("API key auth failed for path %s", request.path)
                return error_response("Invalid or expired API key", 403)

            if not ApiKeyService.rate_limit_key(raw_key):
                return error_response("API key rate limit exceeded", 429)

            key.last_used_at = datetime.now(timezone.utc)
            key.save()
            g.request_identity = f"api-key:{key.key_prefix}"
            g.request_auth_method = "api_key"
            return fn(*args, **kwargs)

        try:
            verify_jwt_in_request(optional=True)
        except Exception:
            return error_response("Authorization required", 401)

        identity = get_jwt_identity()
        if identity is None:
            return error_response("Authorization required", 401)
        g.request_identity = identity
        g.request_auth_method = "jwt"
        return fn(*args, **kwargs)

    return wrapper
