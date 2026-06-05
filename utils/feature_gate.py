"""
utils/feature_gate.py
Gating decorator for requiring specific feature flags to be enabled.
"""

from functools import wraps
from flask_jwt_extended import get_jwt, verify_jwt_in_request
from utils.response_helper import error_response
from services.feature_flag_service import FeatureFlagService
from logger.unified_logger import app_logger

def require_feature(flag_key: str):
    """
    Decorator that checks if a feature flag is enabled for the current organization.
    Expects JWT context to be established (verify_jwt_in_request).
    If disabled, returns 403 Forbidden.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                verify_jwt_in_request()
            except Exception as e:
                app_logger.warning(f"Feature Gate: Missing or invalid JWT for flag check '{flag_key}': {e}")
                return error_response(message="Authentication required for this resource", status_code=401)

            jwt_data = get_jwt()
            org_id = jwt_data.get("organization_id")
            user_roles = jwt_data.get("roles", [])

            # Superadmin bypasses feature gates entirely
            if "superadmin" in user_roles:
                return func(*args, **kwargs)

            feature_flag_service = FeatureFlagService()
            # Reload from DB specifically to bypass any local class initialization caching
            enabled = feature_flag_service.is_feature_enabled(flag_key, org_id)
            if not enabled:

                app_logger.warning(
                    f"Feature Gate: Feature '{flag_key}' is disabled for organization '{org_id}'"
                )
                return error_response(
                    message="Feature not enabled for your organization",
                    status_code=403
                )

            return func(*args, **kwargs)
        return wrapper
    return decorator
