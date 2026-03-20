"""
Environment Configuration Routes (SuperAdmin)
Allows viewing and updating .env file configurations.
WARNING: This is a highly sensitive administrative interface.
"""

import os
import logging
from flask import Blueprint, jsonify, request, current_app
from flasgger import swag_from
from flask_jwt_extended import get_jwt_identity
from utils.security import require_roles
from utils.response_helper import success_response, error_response
from models.User import Role
from dotenv import set_key, dotenv_values

logger = logging.getLogger(__name__)
env_config_bp = Blueprint("env_config", __name__)

ENV_FILE_PATH = os.path.join(os.getcwd(), ".env")


@env_config_bp.route("/", methods=["GET"])
@swag_from({
    "tags": ["Env_Config"],
    "responses": {
        "200": {"description": "Success"}
    }
})
@require_roles(Role.SUPERADMIN.value)
def get_env_configs():
    """Retrieve all backend environment configurations. SUPERADMIN ONLY."""
    try:
        if not os.path.exists(ENV_FILE_PATH):
            return success_response(data={})
        configs = dotenv_values(ENV_FILE_PATH)
        return success_response(data=configs)
    except Exception as e:
        logger.error(f"Failed to fetch env configs: {e}", exc_info=True)
        return error_response(message="Failed to read configuration", status_code=500)


@env_config_bp.route("/", methods=["PUT", "POST"])
@swag_from({
    "tags": ["Env_Config"],
    "responses": {
        "200": {"description": "Success"}
    }
})
@require_roles(Role.SUPERADMIN.value)
def update_env_configs():
    """Update backend environment configurations. SUPERADMIN ONLY."""
    data = request.get_json(silent=True)
    if not data:
        return error_response(message="Request body is required", status_code=400)
    try:
        # Create .env file if it does not exist
        if not os.path.exists(ENV_FILE_PATH):
            with open(ENV_FILE_PATH, "a") as f:
                pass

        for key, value in data.items():
            set_key(ENV_FILE_PATH, key, str(value))

        admin_id = get_jwt_identity()
        current_app.logger.info(
            f"Sensitive environment configurations modified by super-admin {admin_id}"
        )

        configs = dotenv_values(ENV_FILE_PATH)
        return success_response(data=configs)
    except Exception as e:
        logger.error(f"Failed to update env configs: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)
