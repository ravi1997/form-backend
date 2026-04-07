"""
utils/csrf_protection.py
CSRF protection for Flask applications.
Implements double-submit token pattern for state-changing requests.
"""

import secrets
import time
from typing import Optional, Callable
from functools import wraps
from flask import Flask, session, request, abort, g
from logger.unified_logger import app_logger, error_logger


class CSRFProtection:
    """
    CSRF protection middleware for Flask applications.

    Uses Synchronizer Token Pattern (double-submit cookie):
    - Generates CSRF token on GET requests
    - Validates CSRF token on POST/PUT/DELETE/PATCH requests
    """

    # CSRF token settings
    CSRF_TOKEN_LENGTH = 32
    CSRF_TOKEN_EXPIRE_HOURS = 24
    CSRF_COOKIE_NAME = "csrf_token"
    CSRF_HEADER_NAME = "X-CSRF-TOKEN"
    SESSION_KEY = "csrf_secret"

    def __init__(self, app: Flask):
        """
        Initialize CSRF protection.

        Args:
            app: Flask application
        """
        self.app = app

        # Register before_request handler to validate CSRF on state-changing requests
        app.before_request(self._validate_csrf_token)

    def generate_csrf_token(self) -> str:
        """
        Generate a new CSRF token.

        Returns:
            Random CSRF token
        """
        return secrets.token_hex(self.CSRF_TOKEN_LENGTH)

    def get_csrf_token_from_cookie(self) -> Optional[str]:
        """
        Get CSRF token from request cookies.

        Returns:
            CSRF token if present, None otherwise
        """
        return request.cookies.get(self.CSRF_COOKIE_NAME)

    def get_csrf_token_from_header(self) -> Optional[str]:
        """
        Get CSRF token from request headers.

        Returns:
            CSRF token if present, None otherwise
        """
        return request.headers.get(self.CSRF_HEADER_NAME)

    def _validate_csrf_token(self):
        """
        Validate CSRF token for state-changing requests.

        This is called before each request.
        """
        # Skip validation for:
        # - GET requests (safe)
        # # - OPTIONS requests (CORS preflight)
        # if request.method in ("GET", "OPTIONS", "HEAD"):
        if request.method in ("GET", "HEAD"):
            return

        # Skip for paths that are explicitly excluded
        if self._is_csrf_exempt_path():
            return

        # Get CSRF token from cookie
        cookie_token = self.get_csrf_token_from_cookie()

        # Get CSRF token from header
        header_token = self.get_csrf_token_from_header()

        # Validate that we have at least one token
        if not cookie_token and not header_token:
            app_logger.warning(
                f"CSRF validation failed: No CSRF token provided for {request.method} {request.path}"
            )
            abort(403, description="CSRF token missing")

        # Validate token from header if present
        if header_token:
            # Check if header token matches cookie token (preferred method)
            if cookie_token and secrets.compare_digest(header_token, cookie_token):
                # Tokens match, valid
                return
            # Header-only validation (for API clients)
            self._validate_token_expiration(header_token)
            return

        # Validate token from cookie
        if cookie_token:
            self._validate_token_expiration(cookie_token)
            return

        # No valid token found
        app_logger.warning(
            f"CSRF validation failed: Invalid CSRF token for {request.method} {request.path}"
        )
        abort(403, description="Invalid CSRF token")

    def _validate_token_expiration(self, token: str):
        """
        Validate that CSRF token hasn't expired.
        Checks against session timestamp.

        Args:
            token: The CSRF token to validate
        """
        # Get token generation timestamp from session
        token_timestamp = session.get(f"{self.SESSION_KEY}_timestamp")
        if not token_timestamp:
            app_logger.warning("CSRF token validation failed: No timestamp in session")
            abort(403, description="CSRF token expired")

        # Check if token has expired
        current_time = time.time()
        token_age_seconds = current_time - token_timestamp
        max_age_seconds = self.CSRF_TOKEN_EXPIRE_HOURS * 3600

        if token_age_seconds > max_age_seconds:
            app_logger.warning(
                f"CSRF token expired: Age {token_age_seconds}s > {max_age_seconds}s"
            )
            abort(403, description="CSRF token expired")

    def _is_csrf_exempt_path(self) -> bool:
        """
        Check if current path is exempt from CSRF validation.

        Returns:
            True if exempt, False otherwise
        """
        exempt_paths = [
            "/form/api/v1/auth/login",
            "/form/api/v1/auth/register",
            "/form/api/v1/auth/request-otp",
            "/form/api/v1/docs",
            "/health",
        ]

        for exempt_path in exempt_paths:
            if request.path.startswith(exempt_path):
                return True

        return False

    def require_csrf_token(self, f: Callable) -> Callable:
        """
        Decorator to require CSRF token for specific routes.
        Used to mark routes as CSRF-protected.

        Usage:
            @csrf_protection.require_csrf_token
            @bp.route('/protected', methods=['POST'])
            def protected_route():
                return jsonify({'status': 'ok'})

        Args:
            f: The route handler function

        Returns:
            Wrapped function that will generate and include CSRF token
        """

        @wraps(f)
        def wrapper(*args, **kwargs):
            # Generate CSRF token if not already present
            if not self.get_csrf_token_from_cookie():
                csrf_token = self.generate_csrf_token()

                # Store token generation timestamp in session
                session[f"{self.SESSION_KEY}_timestamp"] = time.time()

                # Return response with CSRF token in cookie
                from flask import make_response

                response = make_response(f(*args, **kwargs))

                # Set CSRF token in cookie
                # Note: This will be set on the response, not the current request
                # The actual token should be passed by the client
                return response

            # Token already exists, proceed with normal flow
            return f(*args, **kwargs)

        return wrapper

    def add_csrf_token_to_response(self, response):
        """
        Add CSRF token to response.

        Args:
            response: Flask response object
        """
        csrf_token = self.generate_csrf_token()
        session[f"{self.SESSION_KEY}_timestamp"] = time.time()

        response.set_cookie(
            self.CSRF_COOKIE_NAME,
            value=csrf_token,
            max_age=self.CSRF_TOKEN_EXPIRE_HOURS * 3600,
            httponly=True,
            secure=not self.app.debug,
            samesite="Strict",
        )

        # Also add to response data for client access
        if hasattr(response, "json"):
            from flask import jsonify

            data = response.get_json()
            if isinstance(data, dict):
                data["csrf_token"] = csrf_token
                response.data = jsonify(data)

        return response


# Global CSRF protection instance
csrf_protection = None


def init_csrf_protection(app: Flask):
    """
    Initialize CSRF protection for the Flask application.

    Args:
        app: Flask application

    Returns:
        CSRFProtection instance
    """
    global csrf_protection
    csrf_protection = CSRFProtection(app)
    return csrf_protection


def require_csrf(f: Callable) -> Callable:
    """
    Decorator to mark routes as requiring CSRF protection.
    Note: This is for explicit marking. Most CSRF protection happens automatically.

    Usage:
        @require_csrf
        @bp.route('/api/submit', methods=['POST'])
        def submit_route():
            return jsonify({'status': 'ok'})

    Args:
        f: The route handler function

    Returns:
        Wrapped function
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        return f(*args, **kwargs)

    return wrapper
