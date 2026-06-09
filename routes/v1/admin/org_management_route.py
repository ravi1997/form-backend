"""
routes/v1/admin/org_management_route.py
API endpoints for Superadmins to manage Enterprise Organizations.
"""

from flask import Blueprint, request
from flasgger import swag_from
from utils.security import require_roles
from utils.response_helper import success_response, error_response
from services.org_service import OrgService
from schemas.org import OrgCreateSchema, OrgUpdateStatusSchema, OrgAssignAdminSchema
from logger.unified_logger import app_logger, error_logger
from pydantic import ValidationError as PydanticValidationError
from utils.exceptions import NotFoundError, ValidationError

org_management_bp = Blueprint("org_management", __name__)
org_service = OrgService()

@org_management_bp.route("/", methods=["POST"])
@swag_from({
    "tags": ["Organization Management"],
    "summary": "Create an Enterprise Organization (Superadmin only)",
    "description": "Registers a new organization and atomically configures its default tenant settings/quotas.",
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "required": ["organization_id", "name", "display_name"],
                "properties": {
                    "organization_id": {"type": "string", "example": "tesla"},
                    "name": {"type": "string", "example": "Tesla Inc."},
                    "display_name": {"type": "string", "example": "Tesla"},
                    "contact_email": {"type": "string", "example": "admin@tesla.com"},
                    "description": {"type": "string", "example": "Tesla Enterprise Account"},
                    "metadata": {"type": "object", "example": {"region": "US"}}
                }
            }
        }
    ],
    "responses": {
        "200": {"description": "Organization created successfully"},
        "400": {"description": "Validation or duplicate key error"},
        "403": {"description": "Forbidden - Superadmin only"},
    }
})
@require_roles("superadmin")
def create_org():
    app_logger.info("Entering create_org endpoint")
    try:
        body = request.get_json() or {}
        schema = OrgCreateSchema(**body)
        res = org_service.create_org(schema)
        return success_response(data=res.model_dump(), message="Organization created successfully")
    except ValidationError as e:
        return error_response(message=str(e), status_code=400)
    except NotFoundError as e:
        return error_response(message=str(e), status_code=404)
    except PydanticValidationError as e:
        return error_response(message=str(e), status_code=400)
    except Exception as e:
        error_logger.error(f"Error creating organization: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)

@org_management_bp.route("/", methods=["GET"])
@swag_from({
    "tags": ["Organization Management"],
    "summary": "List all organizations (Superadmin only)",
    "responses": {
        "200": {"description": "Organizations listed successfully"},
        "403": {"description": "Forbidden - Superadmin only"},
    }
})
@require_roles("superadmin")
def get_all_orgs():
    app_logger.info("Entering get_all_orgs endpoint")
    try:
        orgs = org_service.get_all_orgs()
        return success_response(data=[o.model_dump() for o in orgs])
    except ValidationError as e:
        return error_response(message=str(e), status_code=400)
    except NotFoundError as e:
        return error_response(message=str(e), status_code=404)
    except Exception as e:
        error_logger.error(f"Error listing organizations: {e}", exc_info=True)
        return error_response(message=str(e), status_code=500)

@org_management_bp.route("/<org_id>/status", methods=["PUT"])
@swag_from({
    "tags": ["Organization Management"],
    "summary": "Suspend or activate an organization (Superadmin only)",
    "parameters": [
        {"name": "org_id", "in": "path", "type": "string", "required": True},
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "required": ["status"],
                "properties": {
                    "status": {"type": "string", "enum": ["active", "suspended"], "example": "suspended"}
                }
            }
        }
    ],
    "responses": {
        "200": {"description": "Organization status updated successfully"},
        "400": {"description": "Invalid status value"},
        "404": {"description": "Organization not found"},
        "403": {"description": "Forbidden - Superadmin only"},
    }
})
@require_roles("superadmin")
def update_status(org_id):
    app_logger.info(f"Entering update_status endpoint for org: {org_id}")
    try:
        body = request.get_json() or {}
        schema = OrgUpdateStatusSchema(**body)
        res = org_service.update_status(org_id, schema.status)
        return success_response(data=res.model_dump(), message="Organization status updated successfully")
    except ValidationError as e:
        return error_response(message=str(e), status_code=400)
    except NotFoundError as e:
        return error_response(message=str(e), status_code=404)
    except PydanticValidationError as e:
        return error_response(message=str(e), status_code=400)
    except Exception as e:
        error_logger.error(f"Error updating status for org {org_id}: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)

@org_management_bp.route("/<org_id>/admin", methods=["PUT"])
@swag_from({
    "tags": ["Organization Management"],
    "summary": "Assign an administrator user to an organization (Superadmin only)",
    "parameters": [
        {"name": "org_id", "in": "path", "type": "string", "required": True},
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "required": ["admin_user_id"],
                "properties": {
                    "admin_user_id": {"type": "string", "example": "5a41bdf0-c8e9-4e78-9588-e21d6e4cbab3"}
                }
            }
        }
    ],
    "responses": {
        "200": {"description": "Organization admin assigned successfully"},
        "404": {"description": "Organization or user not found"},
        "403": {"description": "Forbidden - Superadmin only"},
    }
})
@require_roles("superadmin")
def assign_admin(org_id):
    app_logger.info(f"Entering assign_admin endpoint for org: {org_id}")
    try:
        body = request.get_json() or {}
        schema = OrgAssignAdminSchema(**body)
        res = org_service.assign_admin(org_id, schema.admin_user_id)
        return success_response(data=res.model_dump(), message="Organization admin assigned successfully")
    except ValidationError as e:
        return error_response(message=str(e), status_code=400)
    except NotFoundError as e:
        return error_response(message=str(e), status_code=404)
    except PydanticValidationError as e:
        return error_response(message=str(e), status_code=400)
    except Exception as e:
        error_logger.error(f"Error assigning admin for org {org_id}: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)

@org_management_bp.route("/<org_id>/stats", methods=["GET"])
@swag_from({
    "tags": ["Organization Management"],
    "summary": "Retrieve standard organization metrics (Admin and Superadmin)",
    "parameters": [
        {"name": "org_id", "in": "path", "type": "string", "required": True}
    ],
    "responses": {
        "200": {"description": "Organization stats retrieved successfully"},
        "404": {"description": "Organization not found"},
        "403": {"description": "Forbidden - Requires admin/superadmin role"},
    }
})
@require_roles("admin", "superadmin")
def get_stats(org_id):
    app_logger.info(f"Entering get_stats endpoint for org: {org_id}")
    try:
        res = org_service.get_stats(org_id)
        return success_response(data=res)
    except ValidationError as e:
        return error_response(message=str(e), status_code=400)
    except NotFoundError as e:
        return error_response(message=str(e), status_code=404)
    except Exception as e:
        error_logger.error(f"Error fetching stats for org {org_id}: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)
