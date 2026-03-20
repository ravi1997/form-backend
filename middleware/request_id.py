import uuid
from flask import request, g
from logger.unified_logger import app_logger

def setup_request_id(app):
    @app.before_request
    def add_request_id():
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        g.request_id = request_id
        
    @app.after_request
    def log_request(response):
        # Optional: Add request ID to response headers
        response.headers["X-Request-ID"] = getattr(g, "request_id", "unknown")
        return response
