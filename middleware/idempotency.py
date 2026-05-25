"""
middleware/idempotency.py — Request idempotency enforcement.

For state-changing endpoints (POST/PUT/PATCH/DELETE), clients may send an
`X-Idempotency-Key` header. If we've seen this key before, we replay the
cached response instead of executing the handler again.

This prevents duplicate form submissions on slow networks / mobile retries.

Usage: registered automatically in app.py via init_idempotency_middleware().
"""

import json
import hashlib
from datetime import datetime, timezone, timedelta
from functools import wraps
from typing import Optional

from flask import request, g, current_app

# TTL for idempotency records in Redis (24 hours)
IDEMPOTENCY_TTL = 86400

# Only enforce on these HTTP methods
IDEMPOTENCY_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Only enforce on paths containing these prefixes (skip health, auth refresh, etc.)
IDEMPOTENCY_PATH_PREFIXES = ("/form/api/v1/forms/", "/form/api/v1/dashboards/")

# Paths that are excluded even if they match a prefix
IDEMPOTENCY_EXCLUDED_PATHS = {
    "/form/api/v1/auth/login",
    "/form/api/v1/auth/refresh",
    "/form/api/v1/auth/logout",
    "/form/api/v1/auth/request-otp",
    "/form/api/v1/auth/otp/request",
}


def _get_idempotency_key() -> Optional[str]:
    """Extract and validate the client-supplied idempotency key."""
    key = request.headers.get("X-Idempotency-Key", "").strip()
    if not key or len(key) > 128:
        return None
    return key


def _cache_key(org_id: str, key: str) -> str:
    """Build the Redis cache key for an idempotency record."""
    raw = f"idempotency:{org_id}:{key}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _should_enforce() -> bool:
    """Return True if idempotency enforcement applies to this request."""
    if request.method not in IDEMPOTENCY_METHODS:
        return False
    path = request.path
    if path in IDEMPOTENCY_EXCLUDED_PATHS:
        return False
    return any(path.startswith(p) for p in IDEMPOTENCY_PATH_PREFIXES)


def init_idempotency_middleware(app):
    """Register before/after request hooks on the Flask app."""

    @app.before_request
    def check_idempotency():
        """If key seen, short-circuit with cached response."""
        if not _should_enforce():
            return None

        key = _get_idempotency_key()
        if not key:
            return None

        org_id = getattr(g, "organization_id", "anon")
        redis_key = _cache_key(org_id, key)

        try:
            from extensions import redis_client
            cached = redis_client.get(redis_key)
            if cached:
                import flask
                data = json.loads(cached)
                response = flask.Response(
                    response=data["body"],
                    status=data["status"],
                    headers={"Content-Type": "application/json",
                             "X-Idempotency-Replayed": "true"},
                )
                return response
            # Mark as in-flight
            g._idempotency_key = key
            g._idempotency_redis_key = redis_key
        except Exception:
            # Idempotency is best-effort; don't break the request
            pass

        return None

    @app.after_request
    def store_idempotency(response):
        """Cache successful (2xx) response body for the idempotency key."""
        if not _should_enforce():
            return response

        key = getattr(g, "_idempotency_key", None)
        redis_key = getattr(g, "_idempotency_redis_key", None)
        if not key or not redis_key:
            return response

        if 200 <= response.status_code < 300:
            try:
                from extensions import redis_client
                payload = json.dumps({
                    "body": response.get_data(as_text=True),
                    "status": response.status_code,
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                })
                redis_client.setex(redis_key, IDEMPOTENCY_TTL, payload)
            except Exception:
                pass  # best-effort

        return response
