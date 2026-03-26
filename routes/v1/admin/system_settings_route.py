"""
System Settings Routes (Admin)
Delegates all settings logic to SystemSettingsService.
"""

from flask import Blueprint, jsonify, request, current_app
from flasgger import swag_from
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.settings_service import SystemSettingsService, SystemSettingsUpdateSchema
from utils.security import require_roles
from utils.response_helper import success_response, error_response
from models.User import Role
from logger.unified_logger import app_logger, error_logger, audit_logger

settings_service = SystemSettingsService()
system_settings_bp = Blueprint("system_settings", __name__)


@system_settings_bp.route("/", methods=["GET"])
@swag_from({
    "tags": [
        "System_Settings"
    ],
    "responses": {
        "200": {
            "description": "Retrieve the global system configuration."
        }
    }
})
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def get_system_settings():
    """Retrieve the global system configuration."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Entering get_system_settings by admin: {admin_id}")
    try:
        result = settings_service.get_settings()
        app_logger.info("Exiting get_system_settings successfully")
        return success_response(data=result.model_dump())
    except Exception as e:
        error_logger.error(f"Failed to fetch system settings: {e}", exc_info=True)
        return error_response(message="Failed to retrieve configuration", status_code=500)


@system_settings_bp.route("/", methods=["PUT"])
@swag_from({
    "tags": [
        "System_Settings"
    ],
    "responses": {
        "200": {
            "description": "Update the global system configuration."
        }
    },
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "schema": {
                "$ref": "#/definitions/SystemSettingsUpdateSchema"
            }
        }
    ]
})
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def update_system_settings():
    """Update the global system configuration."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Entering update_system_settings by admin: {admin_id}")
    data = request.get_json(silent=True)
    if not data:
        app_logger.warning(f"update_system_settings failed: no data provided by admin: {admin_id}")
        return error_response(message="Request body is required", status_code=400)
    try:
        schema = SystemSettingsUpdateSchema(**data)
        result = settings_service.update_settings(schema, updated_by=admin_id)
        
        audit_logger.info(f"System settings updated by admin {admin_id}. Updated fields: {list(data.keys())}")
        app_logger.info(f"Exiting update_system_settings successfully by admin: {admin_id}")
        return success_response(data=result.model_dump())
    except Exception as e:
        error_logger.error(f"Failed to update system settings: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)

