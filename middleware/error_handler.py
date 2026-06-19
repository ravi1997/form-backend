"""
middleware/error_handler.py
Comprehensive error handling middleware with proper logging and response formatting.
Provides structured error responses for different types of errors.
"""

import logging
import traceback
from flask import request, g, jsonify
from werkzeug.exceptions import HTTPException
from utils.exceptions import (
    ValidationError, NotFoundError, ConflictError, StateTransitionError,
    AuthenticationError, AuthorizationError, PluginError, NotificationError
)
from logger.unified_logger import error_logger, audit_logger

logger = logging.getLogger(__name__)


class ErrorHandler:
    """
    Centralized error handling middleware for the Flask application.
    Provides structured error responses and proper logging.
    """
    
    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Register error handlers on the Flask app."""
        
        @app.errorhandler(Exception)
        def handle_unhandled_exception(e):
            """Handle all unhandled exceptions."""
            return self._handle_error(e, 500, "Internal Server Error")
        
        @app.errorhandler(HTTPException)
        def handle_http_exception(e):
            """Handle HTTP exceptions."""
            return self._handle_error(e, e.code, e.description)
        
        @app.errorhandler(ValidationError)
        def handle_validation_error(e):
            """Handle validation errors."""
            return self._handle_error(e, 422, "Validation Error")
        
        @app.errorhandler(NotFoundError)
        def handle_not_found_error(e):
            """Handle not found errors."""
            return self._handle_error(e, 404, "Not Found")
        
        @app.errorhandler(ConflictError)
        def handle_conflict_error(e):
            """Handle conflict errors."""
            return self._handle_error(e, 409, "Conflict")
        
        @app.errorhandler(StateTransitionError)
        def handle_state_transition_error(e):
            """Handle state transition errors."""
            return self._handle_error(e, 422, "State Transition Error")
        
        @app.errorhandler(AuthenticationError)
        def handle_authentication_error(e):
            """Handle authentication errors."""
            return self._handle_error(e, 401, "Authentication Error")
        
        @app.errorhandler(AuthorizationError)
        def handle_authorization_error(e):
            """Handle authorization errors."""
            return self._handle_error(e, 403, "Authorization Error")
        
        @app.errorhandler(PluginError)
        def handle_plugin_error(e):
            """Handle plugin errors."""
            return self._handle_error(e, 500, "Plugin Error")
        
        @app.errorhandler(NotificationError)
        def handle_notification_error(e):
            """Handle notification errors."""
            return self._handle_error(e, 500, "Notification Error")
    
    def _handle_error(self, error, status_code, default_message):
        """
        Handle an error with proper logging and response formatting.
        
        Args:
            error: The error object
            status_code: HTTP status code
            default_message: Default error message
            
        Returns:
            Flask response with error details
        """
        # Get request context
        request_id = getattr(g, 'request_id', 'unknown')
        method = request.method
        path = request.path
        client_ip = request.remote_addr
        
        # Extract error details
        error_message = str(error) if hasattr(error, '__str__') else default_message
        error_type = error.__class__.__name__
        
        # Log the error
        self._log_error(error, status_code, error_message, error_type, 
                       request_id, method, path, client_ip)
        
        # Prepare error response
        error_response = {
            "error": {
                "code": self._get_error_code(error_type),
                "message": error_message or default_message,
                "type": error_type,
                "request_id": request_id
            }
        }
        
        # Add error details if available
        if hasattr(error, 'details') and error.details:
            error_response["error"]["details"] = error.details
        
        # Add stack trace in development
        if hasattr(error, '__traceback__') and self._is_development():
            error_response["error"]["stack_trace"] = traceback.format_exc()
        
        return jsonify(error_response), status_code
    
    def _log_error(self, error, status_code, error_message, error_type,
                  request_id, method, path, client_ip):
        """Log error with appropriate level and context."""
        
        # Create log context
        log_context = {
            "request_id": request_id,
            "method": method,
            "path": path,
            "client_ip": client_ip,
            "status_code": status_code,
            "error_type": error_type,
            "error_message": error_message
        }
        
        # Determine log level
        if status_code >= 500:
            log_level = "error"
            logger_func = error_logger.error
        elif status_code >= 400:
            log_level = "warning"
            logger_func = error_logger.warning
        else:
            log_level = "info"
            logger_func = error_logger.info
        
        # Log the error
        log_message = f"{error_type}: {error_message} - {method} {path} [{status_code}]"
        logger_func(log_message, extra=log_context)
        
        # Audit log for security-related errors
        if status_code in [401, 403]:
            audit_log_message = f"AUDIT: Security error - {error_type} for {method} {path} from {client_ip}"
            audit_logger.warning(audit_log_message, extra=log_context)
    
    def _get_error_code(self, error_type):
        """Get standardized error code from error type."""
        error_code_map = {
            "ValidationError": "VALIDATION_ERROR",
            "NotFoundError": "NOT_FOUND",
            "ConflictError": "CONFLICT",
            "StateTransitionError": "STATE_TRANSITION_ERROR",
            "AuthenticationError": "AUTHENTICATION_ERROR",
            "AuthorizationError": "AUTHORIZATION_ERROR",
            "PluginError": "PLUGIN_ERROR",
            "NotificationError": "NOTIFICATION_ERROR",
            "HTTPException": "HTTP_ERROR",
            "Exception": "INTERNAL_ERROR"
        }
        
        return error_code_map.get(error_type, "UNKNOWN_ERROR")
    
    def _is_development(self):
        """Check if application is in development mode."""
        from config.settings import settings
        return getattr(settings, 'DEBUG', False)


# Global error handler instance
error_handler = ErrorHandler()