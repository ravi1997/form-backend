"""
utils/security.py — Unified Security Utilities
Provides decorators for authentication and role-based access control (RBAC).
Utilizes flask-jwt-extended for secure token handling.
"""

from functools import wraps
from flask import jsonify
from flask_jwt_extended import (
    verify_jwt_in_request,
    get_jwt,
    get_jwt_identity
)
from utils.response_helper import error_response


def require_auth(fn):
    """
    Decorator to ensure a valid JWT is present in the request.
    Automatically handles CSRF if enabled in app config.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        return fn(*args, **kwargs)
    return wrapper


def require_roles(*roles: str):
    """
    Decorator that enforces role-based access control.
    Verifies JWT and checks if the 'roles' claim contains at least one required role.

    Usage:
        @app.route('/admin')
        @require_roles('admin', 'superadmin')
        def admin_view():
            ...
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # 1. Ensure a valid JWT exists
            verify_jwt_in_request()
            
            # 2. Check roles in payload
            jwt_data = get_jwt()
            user_roles = jwt_data.get("roles", [])
            
            if not any(role in user_roles for role in roles):
                return error_response(
                    message=f"Insufficient permissions. Required roles: {', '.join(roles)}",
                    status_code=403
                )
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def handle_unauthorized(e):
    """Global handler for JWT-related unauthorized errors."""
    return error_response(message=str(e) or "Unauthorized", status_code=401)


def handle_forbidden(e):
    """Global handler for permission errors."""
    return error_response(message=str(e) or "Forbidden", status_code=403)
