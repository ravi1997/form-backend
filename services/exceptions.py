"""
services/exceptions.py
Re-exports all service exceptions from the canonical utils.exceptions module.
This shim satisfies internal service imports (from .exceptions import ...)
while keeping the single source of truth in utils/exceptions.py.
"""

from utils.exceptions import (
    ServiceError,
    NotFoundError,
    ValidationError,
    UnauthorizedError,
    ForbiddenError,
    ConflictError,
    StateTransitionError,
)

__all__ = [
    "ServiceError",
    "NotFoundError",
    "ValidationError",
    "UnauthorizedError",
    "ForbiddenError",
    "ConflictError",
    "StateTransitionError",
]
