from flask_jwt_extended import JWTManager, get_jwt
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flasgger import Swagger
from flask import request
import os

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

# Construct storage URI for Limiter
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
limiter_storage = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

limiter = Limiter(
    key_func=tenant_aware_key_func, 
    default_limits=["2000 per hour", "100 per minute"],
    storage_uri=limiter_storage
)
talisman = Talisman()
swagger = Swagger()
