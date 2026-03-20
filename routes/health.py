from flask import Blueprint, jsonify
from config.settings import settings
import logging

health_bp = Blueprint("health_bp", __name__)
logger = logging.getLogger(__name__)

@health_bp.route("/", methods=["GET"])
def health_check():
    """
    Comprehensive health check interrogating critical infrastructure.
    Used by orchestrators to determine service readiness.
    """
    from mongoengine.connection import get_db
    from services.redis_service import redis_service
    
    health_status = {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "env": settings.APP_ENV,
        "dependencies": {
            "mongodb": "unknown",
            "redis": "unknown"
        }
    }
    
    # 1. Check MongoDB
    try:
        get_db().command("ping")
        health_status["dependencies"]["mongodb"] = "connected"
    except Exception as e:
        logger.error(f"Health Check: MongoDB connection failure: {e}")
        health_status["dependencies"]["mongodb"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"
        
    # 2. Check Redis
    try:
        # Check all registered clients
        for client_name in ["cache", "session", "queue"]:
            client = redis_service.get_client(client_name)
            if not client.client.ping():
                 raise ConnectionError(f"Redis client '{client_name}' ping failed")
        health_status["dependencies"]["redis"] = "connected"
    except Exception as e:
        logger.error(f"Health Check: Redis connection failure: {e}")
        health_status["dependencies"]["redis"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"
        
    return jsonify(health_status), 200 if health_status["status"] == "healthy" else 503
