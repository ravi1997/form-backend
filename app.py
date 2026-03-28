"""
app.py — Application Factory
Creates and configures the Flask application, registers all blueprints,
and sets up MongoDB, logging, and Sentry.
"""

from flask import Flask, jsonify
from config.settings import settings
from config.logging import setup_logging
from mongoengine import connect
import logging


def create_app():
    # ── Logging ────────────────────────────────────────────────────────────
    setup_logging()
    logger = logging.getLogger(__name__)

    # ── Tracing (OpenTelemetry) ────────────────────────────────────────────
    from config.tracing import init_tracing
    init_tracing()

    # ── Flask App ───────────────────────────────────────────────────────────
    app = Flask(settings.APP_NAME)
    app.config.from_mapping(
        SECRET_KEY=settings.JWT_SECRET_KEY,
        JWT_SECRET_KEY=settings.JWT_SECRET_KEY,
        JWT_ALGORITHM=settings.JWT_ALGORITHM,
        DEBUG=settings.DEBUG,
        # Securing JWT Cookies
        JWT_TOKEN_LOCATION=["headers", "cookies"],
        JWT_ACCESS_COOKIE_PATH="/form/api/",
        JWT_REFRESH_COOKIE_PATH="/form/api/v1/auth/refresh",
        JWT_COOKIE_SECURE=not settings.DEBUG,
        JWT_COOKIE_HTTPONLY=True,
        JWT_COOKIE_SAMESITE="Strict",
        JWT_COOKIE_CSRF_PROTECT=True,
        JWT_ACCESS_CSRF_HEADER_NAME="X-CSRF-TOKEN-ACCESS",
        JWT_REFRESH_CSRF_HEADER_NAME="X-CSRF-TOKEN-REFRESH",
    )

    # ── JWT, CORS, Limiter & Talisman, Swagger ────────────────────────────────
    from extensions import jwt, cors, limiter, talisman, swagger
    cors.init_app(app)
    jwt.init_app(app)
    
    # Configure Limiter with Redis
    limiter.init_app(app)
    # Note: In a production setup, we would inject the storage URI here
    # from settings.REDIS_HOST/PORT/DB
    
    # Secure headers with Talisman
    talisman.init_app(
        app,
        content_security_policy=None,  # REST API, usually no inline scripts
        force_https=False, # Temporarily disabled for local validation
        strict_transport_security=True,
    )
    
    app.config['SWAGGER'] = {
        "title": settings.APP_NAME,
        "uiversion": 3,
        "specs_route": "/form/docs",
        "static_url_path": "/form/flasgger_static",
        "specs": [
            {
                "endpoint": 'apispec_1',
                "route": '/form/apispec_1.json',
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
            }
        ],
        "swagger_ui": True
    }
    swagger.init_app(app)

    from utils.jwt_handlers import register_jwt_handlers
    register_jwt_handlers(app)

    # ── Middleware ───────────────────────────────────────────────────────────
    from middleware.request_id import setup_request_id
    setup_request_id(app)
    
    from middleware.security_waf import waf
    waf.init_app(app)
    
    from middleware.tenant_db import setup_tenant_db
    setup_tenant_db(app)

    # ── MongoDB ─────────────────────────────────────────────────────────────
    import sys
    try:
        connect(host=settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
        from mongoengine.connection import get_db
        get_db().command("ping")
        logger.info("Connected to MongoDB successfully.")
    except Exception as e:
        logger.critical(f"FATAL: Failed to connect to MongoDB: {e}")
        if settings.APP_ENV != "development":
            sys.exit(1)

    # ── Redis clients setup ─────────────────────────────────────────────────
    try:
        from services.redis_service import redis_service
        from config.redis import RedisConfig

        redis_service.configure_client("cache", RedisConfig(db=settings.REDIS_DB))
        redis_service.configure_client("session", RedisConfig(db=settings.REDIS_DB + 1))
        redis_service.configure_client(
            "queue", RedisConfig(db=settings.CELERY_BROKER_DB)
        )
        if not redis_service.cache.ping():
            raise ConnectionError("Redis ping failed.")
        logger.info("Redis clients configured successfully.")
    except Exception as e:
        logger.critical(f"FATAL: Redis configuration/connection failed: {e}")
        if settings.APP_ENV != "development":
            sys.exit(1)

    # ── Blueprints ──────────────────────────────────────────────────────────
    from routes import register_blueprints
    register_blueprints(app)

    # ── Instrument Flask ──────────────────────────────────────────────────
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    FlaskInstrumentor().instrument_app(app)

    # ── Global Error Handlers ───────────────────────────────────────────────
    from utils.error_handlers import register_error_handlers
    register_error_handlers(app)

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=5000, debug=settings.DEBUG)
