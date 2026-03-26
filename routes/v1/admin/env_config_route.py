"""
Environment Configuration Routes (SuperAdmin)
Allows viewing and updating .env file configurations.
WARNING: This is a highly sensitive administrative interface.
"""

import os
from flask import Blueprint, jsonify, request, current_app
from flasgger import swag_from
from flask_jwt_extended import get_jwt_identity
from utils.security import require_roles
from utils.response_helper import success_response, error_response
from models.User import Role
from dotenv import set_key, dotenv_values
from logger.unified_logger import app_logger, error_logger, audit_logger

env_config_bp = Blueprint("env_config", __name__)

ENV_FILE_PATH = os.path.join(os.getcwd(), ".env")


@env_config_bp.route("/", methods=["GET"])
@swag_from({
    "tags": [
        "Env_Config"
    ],
    "responses": {
        "200": {
            "description": "Retrieve all backend environment configurations. SUPERADMIN ONLY."
        }
    }
})
@require_roles(Role.SUPERADMIN.value)
def get_env_configs():
    """Retrieve all backend environment configurations. SUPERADMIN ONLY."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Entering get_env_configs by super-admin: {admin_id}")
    try:
        if not os.path.exists(ENV_FILE_PATH):
            app_logger.warning(".env file not found, returning empty config")
            return success_response(data={})
        configs = dotenv_values(ENV_FILE_PATH)
        app_logger.info("Exiting get_env_configs successfully")
        return success_response(data=configs)
    except Exception as e:
        error_logger.error(f"Failed to fetch env configs: {e}", exc_info=True)
        return error_response(message="Failed to read configuration", status_code=500)


@env_config_bp.route("/", methods=["PUT", "POST"])
@swag_from({
    "tags": [
        "Env_Config"
    ],
    "responses": {
        "200": {
            "description": "Update backend environment configurations. SUPERADMIN ONLY."
        }
    }
})
@require_roles(Role.SUPERADMIN.value)
def update_env_configs():
    """Update backend environment configurations. SUPERADMIN ONLY."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Entering update_env_configs by super-admin: {admin_id}")
    data = request.get_json(silent=True)
    if not data:
        app_logger.warning(f"update_env_configs failed: no data provided by {admin_id}")
        return error_response(message="Request body is required", status_code=400)
    try:
        # Create .env file if it does not exist
        if not os.path.exists(ENV_FILE_PATH):
            with open(ENV_FILE_PATH, "a") as f:
                pass

        keys_updated = list(data.keys())
        for key, value in data.items():
            set_key(ENV_FILE_PATH, key, str(value))

        audit_logger.info(
            f"Sensitive environment configurations modified by super-admin {admin_id}. Keys: {keys_updated}"
        )

        configs = dotenv_values(ENV_FILE_PATH)
        app_logger.info(f"Exiting update_env_configs successfully. Updated keys: {keys_updated}")
        return success_response(data=configs)
    except Exception as e:
        error_logger.error(f"Failed to update env configs: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)

