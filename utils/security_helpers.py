from functools import wraps
from flask import request, current_app
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
from models.User import User
from models.Form import Form
from utils.exceptions import UnauthorizedError, ForbiddenError, NotFoundError
from utils.response_helper import error_response
from services.access_control_service import AccessControlService


def get_current_user():
    """
    Retrieve current authenticated user from JWT identity.
    """
    user_id = get_jwt_identity()
    if not user_id:
        return None

    # Get user with organization_id from JWT for proper tenant isolation
    from flask_jwt_extended import get_jwt

    jwt_data = get_jwt()
    organization_id = jwt_data.get("organization_id")

    user = User.objects(id=user_id, organization_id=organization_id).first()
    return user


def has_form_permission(user, form, action):
    """
    Centralized check for form permissions using AccessControlService.
    """
    return AccessControlService.check_form_permission(user, form, action)


def require_permission(resource_type, action):
    """
    Decorator to enforce resource-level permissions using AccessControlService.
    Assumes the route has a 'form_id', 'response_id', 'dashboard_id', or 'project_id' parameter.
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

                # Convert string to UUID if necessary
                from uuid import UUID

                try:
                    search_id = UUID(form_id) if isinstance(form_id, str) else form_id
                except ValueError:
                    raise NotFoundError("Invalid form ID format")

                form = Form.objects(id=search_id, is_deleted=False).first()
                if not form:
                    raise NotFoundError("Form not found")

                if not AccessControlService.check_form_permission(user, form, action):
                    raise ForbiddenError(
                        f"Insufficient permissions to {action} this form"
                    )

            elif resource_type == "response":
                response_id = kwargs.get("response_id")
                if not response_id:
                    raise ForbiddenError("Missing response_id for permission check")

                from models.Response import FormResponse

                response = FormResponse.objects(
                    id=response_id, is_deleted=False
                ).first()
                if not response:
                    raise NotFoundError("Response not found")

                if not AccessControlService.check_response_permission(
                    user, response, action
                ):
                    raise ForbiddenError(
                        f"Insufficient permissions to {action} this response"
                    )

            elif resource_type == "dashboard":
                dashboard_id = kwargs.get("dashboard_id")
                if not dashboard_id:
                    slug = kwargs.get("slug")
                    if not slug:
                        raise ForbiddenError("Missing dashboard identifier")
                    from models.Dashboard import Dashboard

                    dashboard = Dashboard.objects(
                        slug=slug, organization_id=user.organization_id
                    ).first()
                else:
                    from models.Dashboard import Dashboard

                    dashboard = Dashboard.objects(
                        id=dashboard_id, organization_id=user.organization_id
                    ).first()
                if not dashboard:
                    raise NotFoundError("Dashboard not found")

                if not AccessControlService.check_dashboard_permission(
                    user, dashboard, action
                ):
                    raise ForbiddenError("Insufficient permissions for this dashboard")

            elif resource_type == "project":
                project_id = kwargs.get("project_id")
                if not project_id:
                    raise ForbiddenError("Missing project_id for permission check")

                from models.Form import Project

                project = Project.objects(id=project_id, is_deleted=False).first()
                if not project:
                    raise NotFoundError("Project not found")

                if not AccessControlService.check_project_permission(
                    user, project, action
                ):
                    raise ForbiddenError("Insufficient permissions for this project")

            else:
                raise ForbiddenError(f"Unknown resource type: {resource_type}")

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
                resource = model_class.objects(
                    id=resource_id, organization_id=user.organization_id
                ).first()
                if not resource:
                    raise NotFoundError(
                        f"{model_class.__name__} not found in your organization"
                    )

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
                resource = model_class.objects(
                    id=resource_id, organization_id=user.organization_id
                ).first()
                if not resource:
                    raise NotFoundError(
                        f"{model_class.__name__} not found in your organization"
                    )

            return fn(*args, **kwargs)

        return wrapper

    return decorator
