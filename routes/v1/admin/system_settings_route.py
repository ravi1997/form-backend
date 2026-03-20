"""
System Settings Routes (Admin)
Delegates all settings logic to SystemSettingsService.
"""

import logging
from flask import Blueprint, jsonify, request, current_app
from flasgger import swag_from
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.settings_service import SystemSettingsService, SystemSettingsUpdateSchema
from utils.security import require_roles
from utils.response_helper import success_response, error_response
from models.User import Role

logger = logging.getLogger(__name__)
settings_service = SystemSettingsService()
system_settings_bp = Blueprint("system_settings", __name__)


@system_settings_bp.route("/", methods=["GET"])
@swag_from({
    "tags": ["System_Settings"],
    "responses": {
        "200": {"description": "Success"}
    }
})
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def get_system_settings():
    """Retrieve the global system configuration."""
    try:
        result = settings_service.get_settings()
        return success_response(data=result.model_dump())
    except Exception as e:
        logger.error(f"Failed to fetch system settings: {e}", exc_info=True)
        return error_response(message="Failed to retrieve configuration", status_code=500)


@system_settings_bp.route("/", methods=["PUT"])
@swag_from({
    "tags": ["System_Settings"],
    "responses": {
        "200": {"description": "Success"}
    }
})
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def update_system_settings():
    """Update the global system configuration."""
    data = request.get_json(silent=True)
    if not data:
        return error_response(message="Request body is required", status_code=400)
    try:
        admin_id = get_jwt_identity()
        schema = SystemSettingsUpdateSchema(**data)
        result = settings_service.update_settings(schema, updated_by=admin_id)
        current_app.logger.info(f"System settings updated by admin {admin_id}")
        return success_response(data=result.model_dump())
    except Exception as e:
        logger.error(f"Failed to update system settings: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)
