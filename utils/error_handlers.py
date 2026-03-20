from utils.response_helper import error_response
from utils.exceptions import ServiceError, NotFoundError, ValidationError, UnauthorizedError, ForbiddenError
from mongoengine import DoesNotExist, ValidationError as MongoValidationError
from logger.unified_logger import get_logger

logger = get_logger(__name__)

def register_error_handlers(app):
    @app.errorhandler(NotFoundError)
    @app.errorhandler(DoesNotExist)
    def handle_not_found(e):
        return error_response(message=str(e) or "Resource not found", status_code=404)

    @app.errorhandler(ValidationError)
    @app.errorhandler(MongoValidationError)
    def handle_validation_error(e):
        details = getattr(e, "details", None)
        return error_response(message=str(e) or "Validation failed", details=details, status_code=422)

    @app.errorhandler(UnauthorizedError)
    def handle_unauthorized_error(e):
        return error_response(message=str(e) or "Unauthorized", status_code=401)

    @app.errorhandler(ForbiddenError)
    def handle_forbidden_error(e):
        return error_response(message=str(e) or "Forbidden", status_code=403)

    @app.errorhandler(ServiceError)
    def handle_service_error(e):
        return error_response(message=str(e), details=e.details, status_code=400)

    @app.errorhandler(404)
    def not_found(e):
        return error_response(message="Resource not found", status_code=404)

    @app.errorhandler(405)
    def method_not_allowed(e):
        return error_response(message="Method not allowed", status_code=405)

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Unhandled server error: {e}", exc_info=True)
        return error_response(message="Internal server error", status_code=500)

    from utils.security import handle_unauthorized, handle_forbidden
    app.register_error_handler(401, handle_unauthorized)
    app.register_error_handler(403, handle_forbidden)
