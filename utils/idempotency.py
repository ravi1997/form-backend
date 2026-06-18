import hashlib
import json
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from mongoengine import NotUniqueError

from models.utility import IdempotencyRecord
from utils.response_helper import error_response
from utils.security_helpers import get_current_user


def require_idempotency(ttl_hours=24):
    """
    Enforce Idempotency-Key on unsafe retryable mutations.

    Replays the first successful JSON response for the same
    tenant/user/route/key/body hash. A reused key with a different body returns
    409.
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = request.headers.get("Idempotency-Key")
            if not key:
                return error_response(
                    message="Idempotency-Key header is required",
                    status_code=400,
                    code="IDEMPOTENCY_KEY_REQUIRED",
                )

            verify_jwt_in_request()
            user = get_current_user()
            user_id = str(get_jwt_identity())
            organization_id = getattr(user, "organization_id", None)
            if not organization_id:
                return error_response(
                    message="Tenant context is required",
                    status_code=400,
                    code="TENANT_CONTEXT_REQUIRED",
                )

            request_hash = _request_hash()
            route = f"{request.method} {request.path}"
            existing = IdempotencyRecord.objects(
                organization_id=organization_id,
                user_id=user_id,
                key=key,
                route=route,
            ).first()

            if existing:
                if existing.request_hash != request_hash:
                    return error_response(
                        message="Idempotency-Key was reused with a different request body",
                        status_code=409,
                        code="IDEMPOTENCY_KEY_REUSED",
                    )
                status_code = int(existing.response_status or "200")
                from flask import jsonify

                return jsonify(existing.response_body), status_code

            response = fn(*args, **kwargs)
            flask_response, status_code = _normalize_response(response)
            if 200 <= status_code < 300:
                try:
                    IdempotencyRecord(
                        organization_id=organization_id,
                        user_id=user_id,
                        key=key,
                        route=route,
                        request_hash=request_hash,
                        response_body=flask_response.get_json(silent=True) or {},
                        response_status=str(status_code),
                        expires_at=datetime.now(timezone.utc)
                        + timedelta(hours=ttl_hours),
                    ).save()
                except NotUniqueError:
                    pass
            return response

        return wrapper

    return decorator


def _request_hash():
    payload = {
        "json": request.get_json(silent=True),
        "args": request.args.to_dict(flat=False),
    }
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _normalize_response(response):
    if isinstance(response, tuple):
        return response[0], response[1]
    return response, getattr(response, "status_code", 200)


def celery_idempotent(ttl_seconds=86400):
    """
    Decorator for Celery tasks to ensure idempotency.
    Checks Redis for an idempotency key (passed as 'idempotency_key' in kwargs).
    If the key is found and completed, skips execution and returns the cached result.
    If the key is found and processing, skips duplicate concurrent execution.
    Stores the result of the task execution upon success.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            from extensions import redis_client
            from logger.unified_logger import app_logger, error_logger

            key = kwargs.get("idempotency_key")
            if not key:
                # If no key is explicitly passed, construct a stable hash of task name + args + kwargs
                import hashlib
                raw_args = json.dumps({"args": args, "kwargs": {k: v for k, v in kwargs.items() if k != "idempotency_key"}}, sort_keys=True, default=str)
                key_hash = hashlib.sha256(raw_args.encode("utf-8")).hexdigest()
                key = f"celery:{func.__name__}:{key_hash}"
            else:
                key = f"celery:{func.__name__}:{key}"

            redis_key = f"idempotency:{key}"
            
            try:
                state = redis_client.get(redis_key)
                if state:
                    state_val = json.loads(state)
                    if state_val.get("status") == "processing":
                        app_logger.info(f"Task {func.__name__} with key {key} is already processing. Skipping duplicate execution.")
                        return {"status": "skipped", "reason": "already_processing"}
                    elif state_val.get("status") == "completed":
                        app_logger.info(f"Task {func.__name__} with key {key} already completed. Replaying cached result.")
                        return state_val.get("result")
                
                # Mark as processing
                redis_client.setex(redis_key, 3600, json.dumps({"status": "processing"}))
            except Exception as e:
                error_logger.warning(f"Failed to check/set Celery idempotency key {redis_key}: {e}")

            # Remove idempotency_key from kwargs before calling the function
            kwargs_clean = kwargs.copy()
            kwargs_clean.pop("idempotency_key", None)
            try:
                result = func(self, *args, **kwargs_clean)
                
                try:
                    redis_client.setex(
                        redis_key,
                        ttl_seconds,
                        json.dumps({"status": "completed", "result": result, "completed_at": datetime.now(timezone.utc).isoformat()})
                    )
                except Exception as e:
                    error_logger.warning(f"Failed to cache Celery task completion for key {redis_key}: {e}")
                
                return result
            except Exception as e:
                try:
                    redis_client.delete(redis_key)
                except Exception as del_err:
                    error_logger.warning(f"Failed to clear Celery idempotency key on failure {redis_key}: {del_err}")
                raise e
        return wrapper
    return decorator
