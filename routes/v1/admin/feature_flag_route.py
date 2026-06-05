"""
routes/v1/admin/feature_flag_route.py
API endpoints for managing Feature Flags.
"""

from flask import Blueprint, request
from flasgger import swag_from
from utils.security import require_roles
from utils.response_helper import success_response, error_response
from services.feature_flag_service import FeatureFlagService
from schemas.feature_flag import FeatureFlagUpdateSchema, FeatureFlagOrgOverrideSchema
from logger.unified_logger import app_logger, error_logger
from pydantic import ValidationError as PydanticValidationError

feature_flag_bp = Blueprint("feature_flag", __name__)
feature_flag_service = FeatureFlagService()

@feature_flag_bp.route("/", methods=["GET"])
@swag_from({
    "tags": ["Feature Flags"],
    "summary": "Get all feature flags and overrides (Superadmin only)",
    "responses": {
        "200": {"description": "Feature flags retrieved successfully"},
        "403": {"description": "Forbidden - Superadmin only"},
    }
})
@require_roles("superadmin")
def get_all_flags():
    app_logger.info("Entering get_all_flags endpoint")
    try:
        flags = feature_flag_service.get_all_flags()
        return success_response(data=[f.model_dump() for f in flags])
    except Exception as e:
        error_logger.error(f"Error listing feature flags: {e}", exc_info=True)
        return error_response(message=str(e), status_code=500)

@feature_flag_bp.route("/<flag_key>", methods=["PUT"])
@swag_from({
    "tags": ["Feature Flags"],
    "summary": "Update global feature flag default state (Superadmin only)",
    "parameters": [
        {"name": "flag_key", "in": "path", "type": "string", "required": True},
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "required": ["is_enabled"],
                "properties": {
                    "is_enabled": {"type": "boolean", "example": True}
                }
            }
        }
    ],
    "responses": {
        "200": {"description": "Global feature flag updated successfully"},
        "404": {"description": "Feature flag not found"},
        "403": {"description": "Forbidden - Superadmin only"},
    }
})
@require_roles("superadmin")
def update_global_flag(flag_key):
    app_logger.info(f"Entering update_global_flag endpoint for flag: {flag_key}")
    try:
        body = request.get_json() or {}
        schema = FeatureFlagUpdateSchema(**body)
        res = feature_flag_service.update_global_flag(flag_key, schema.is_enabled)
        return success_response(data=res.model_dump(), message="Global feature flag updated successfully")
    except PydanticValidationError as e:
        return error_response(message=str(e), status_code=400)
    except Exception as e:
        error_logger.error(f"Error updating global flag {flag_key}: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)

@feature_flag_bp.route("/<flag_key>/override/<org_id>", methods=["PUT"])
@swag_from({
    "tags": ["Feature Flags"],
    "summary": "Configure feature flag override for a specific organization (Superadmin only)",
    "parameters": [
        {"name": "flag_key", "in": "path", "type": "string", "required": True},
        {"name": "org_id", "in": "path", "type": "string", "required": True},
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "required": ["is_enabled"],
                "properties": {
                    "is_enabled": {"type": "boolean", "example": True}
                }
            }
        }
    ],
    "responses": {
        "200": {"description": "Organization feature override saved successfully"},
        "404": {"description": "Feature flag not found"},
        "403": {"description": "Forbidden - Superadmin only"},
    }
})
@require_roles("superadmin")
def set_org_override(flag_key, org_id):
    app_logger.info(f"Entering set_org_override endpoint for flag: {flag_key}, org: {org_id}")
    try:
        body = request.get_json() or {}
        schema = FeatureFlagOrgOverrideSchema(**body)
        res = feature_flag_service.set_org_override(flag_key, org_id, schema.is_enabled)
        return success_response(data=res.model_dump(), message="Organization feature override saved successfully")
    except PydanticValidationError as e:
        return error_response(message=str(e), status_code=400)
    except Exception as e:
        error_logger.error(f"Error setting override for flag {flag_key} on org {org_id}: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)
