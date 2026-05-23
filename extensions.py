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

# --- Swagger Global Configuration ---
template = {
    "swagger": "2.0",
    "info": {
        "title": "Forms Backend API",
        "description": "Comprehensive API for managing forms, responses, and AI analysis.",
        "version": "1.0.0"
    },
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "JWT Authorization header using the Bearer scheme. Example: \"Authorization: Bearer {token}\""
        }
    }
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
