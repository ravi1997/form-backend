class ServiceError(Exception):
    """Base exception for all service-level errors."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(ServiceError):
    """Raised when a requested resource is not found."""


class ValidationError(ServiceError):
    """Raised when business logic validation fails."""


class UnauthorizedError(ServiceError):
    """Raised when authentication fails or is missing."""


class ForbiddenError(ServiceError):
    """Raised when a user lacks permission to perform an action."""


class ConflictError(ServiceError):
    """Raised when an operation conflicts with the current state."""


class StateTransitionError(ServiceError):
    """Raised when an invalid state transition is attempted."""
