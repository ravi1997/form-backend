from functools import wraps
from flask import request, current_app
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
from models.User import User
from models.Form import Form
from utils.exceptions import UnauthorizedError, ForbiddenError, NotFoundError
from utils.response_helper import error_response

def get_current_user():
    """
    Retrieve the current authenticated user from the JWT identity.
    """
    user_id = get_jwt_identity()
    if not user_id:
        return None
    user = User.objects(id=user_id).first()
    return user

def has_form_permission(user, form, action):
    """
    Centralized check for form permissions.
    """
    if not user or not form:
        return False
        
    user_id_str = str(user.id)
    
    # 1. Multi-tenant check: User's organization must match the form's organization
    if user.organization_id != form.organization_id:
        current_app.logger.warning(f"Tenant violation: User {user_id_str} (org: {user.organization_id}) attempted to access form {form.id} (org: {form.organization_id})")
        return False

    # 2. Superadmin / Admin escape hatch
    if user.role in ["superadmin", "admin"]:
        return True
        
    # 3. Creator always has permission
    if str(form.created_by) == user_id_str:
        return True
        
    # 4. Access Policy / Roles check
    # Note: This logic should match the detailed checks in form_helper.py
    # but consolidated for performance and safety.
    from routes.v1.form.helper import has_form_permission as legacy_check
    return legacy_check(user, form, action)

def require_permission(resource_type, action):
    """
    Decorator to enforce resource-level permissions.
    Assumes the route has a 'form_id' or 'response_id' parameter.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = get_current_user()
            if not user:
                raise UnauthorizedError("User not found")
                
            if resource_type == "form":
                form_id = kwargs.get("form_id")
                if not form_id:
                    raise ForbiddenError("Missing form_id for permission check")
                
                form = Form.objects(id=form_id, is_deleted=False).first()
                if not form:
                    raise NotFoundError("Form not found")
                    
                if not has_form_permission(user, form, action):
                    raise ForbiddenError(f"Insufficient permissions to {action} this form")
            
            if resource_type == "dashboard":
                dashboard_id = kwargs.get("dashboard_id")
                if not dashboard_id:
                    slug = kwargs.get("slug")
                    if not slug:
                         raise ForbiddenError("Missing dashboard identifier")
                    from models.Dashboard import Dashboard
                    dashboard = Dashboard.objects(slug=slug, organization_id=user.organization_id).first()
                else:
                    from models.Dashboard import Dashboard
                    dashboard = Dashboard.objects(id=dashboard_id, organization_id=user.organization_id).first()
                if not dashboard:
                    raise NotFoundError("Dashboard not found")
                if user.organization_id != dashboard.organization_id:
                     raise ForbiddenError("Insufficient permissions for this dashboard")

            return fn(*args, **kwargs)
        return wrapper
    return decorator

def require_org_match(model_class):
    """
    Decorator to ensure the requested resource belongs to the user's organization.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = get_current_user()
            
            # Extract ID from kwargs (form_id, user_id, etc.)
            resource_id = None
            for key in ["id", "form_id", "user_id", "project_id"]:
                if key in kwargs:
                    resource_id = kwargs[key]
                    break
            
            if resource_id:
                resource = model_class.objects(id=resource_id, organization_id=user.organization_id).first()
                if not resource:
                    raise NotFoundError(f"{model_class.__name__} not found in your organization")
                    
            return fn(*args, **kwargs)
        return wrapper
    return decorator
