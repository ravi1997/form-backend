from flask import request, g
from flask_jwt_extended import verify_jwt_in_request, get_jwt
from utils.permission_validator import permission_validator
from utils.response_helper import error_response
from logger.unified_logger import app_logger, audit_logger

def setup_rbac_matrix(app):
    """
    Middleware that enforces dynamic role-based access control (RBAC) 
    using the permissions matrix defined in config/permissions.yaml.
    """
    
    @app.before_request
    def check_rbac_matrix():
        # Skip OPTIONS preflight requests
        if request.method == "OPTIONS":
            return

        # Resolve path
        path = request.path
        method = request.method

        # 1. Match route against permission matrix
        required_permission = permission_validator.match_route_permission(method, path)
        if not required_permission:
            # Endpoint is not explicitly protected in permissions.yaml
            return

        app_logger.info(f"RBAC: Route '{method} {path}' requires permission '{required_permission}'. Checking...")

        # 2. Enforce authentication
        try:
            verify_jwt_in_request()
        except Exception as e:
            app_logger.warning(f"RBAC: Missing or invalid JWT for protected route '{method} {path}': {e}")
            return error_response(
                message="Authentication required for this resource",
                status_code=401
            )

        # 3. Retrieve user roles from JWT
        jwt_data = get_jwt()
        user_roles = jwt_data.get("roles", [])
        user_id = jwt_data.get("sub", "unknown")
        org_id = jwt_data.get("organization_id", "unknown")

        # 4. Check permissions
        if not permission_validator.has_permission(user_roles, required_permission):
            warn_msg = f"RBAC Denied: User '{user_id}' with roles {user_roles} in org '{org_id}' lacks permission '{required_permission}' for '{method} {path}'"
            app_logger.warning(warn_msg)
            audit_logger.warning(f"AUDIT: Unauthorized access attempt: {warn_msg}")
            return error_response(
                message="Insufficient permissions for this resource",
                status_code=403
            )

        app_logger.info(f"RBAC Approved: User '{user_id}' granted access to '{method} {path}' via permission '{required_permission}'")

    return app
