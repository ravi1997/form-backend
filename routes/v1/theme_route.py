from flasgger import swag_from
from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from logger.unified_logger import app_logger, error_logger, audit_logger
from models.Theme import Theme
from schemas.theme import ThemeCreateSchema, ThemeUpdateSchema
from services.theme_service import ThemeService
from utils.response_helper import BaseSerializer, success_response
from utils.security_helpers import get_current_user

theme_bp = Blueprint("themes", __name__)
theme_service = ThemeService()


def _serialize_theme(theme):
    return BaseSerializer.clean_dict(theme.to_dict())


@theme_bp.route("/", methods=["GET"])
@swag_from({"tags": ["Themes"], "responses": {"200": {"description": "Themes listed"}}})
@jwt_required()
def list_themes():
    """List all themes for the organization."""
    current_user = get_current_user()
    query = {"is_deleted": False}
    if "superadmin" not in (current_user.roles or []):
        query["organization_id"] = current_user.organization_id
    themes = Theme.objects(**query).order_by("-updated_at")
    return success_response(data=[_serialize_theme(theme) for theme in themes])


@theme_bp.route("/", methods=["POST"])
@swag_from({"tags": ["Themes"], "responses": {"201": {"description": "Theme created"}}})
@jwt_required()
def create_theme():
    """Create a new custom theme."""
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    data["organization_id"] = current_user.organization_id
    data["created_by"] = str(current_user.id)
    if "superadmin" not in (current_user.roles or []):
        data["is_global"] = False
    schema = ThemeCreateSchema(**data)
    theme = theme_service.create_theme(schema)
    audit_logger.info(f"Theme {theme.id} created by user {current_user.id}")
    return success_response(data=theme.model_dump(), message="Theme created", status_code=201)


@theme_bp.route("/<theme_id>", methods=["PUT"])
@swag_from({"tags": ["Themes"], "responses": {"200": {"description": "Theme updated"}}})
@jwt_required()
def update_theme(theme_id):
    """Update custom theme settings."""
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    data.pop("organization_id", None)
    data.pop("created_by", None)
    if "superadmin" not in (current_user.roles or []):
        data["is_global"] = False
    schema = ThemeUpdateSchema(**data)
    theme = theme_service.update_theme(
        theme_id, schema, organization_id=current_user.organization_id
    )
    audit_logger.info(f"Theme {theme_id} updated by user {current_user.id}")
    return success_response(data=theme.model_dump(), message="Theme updated")


@theme_bp.route("/<theme_id>", methods=["DELETE"])
@swag_from({"tags": ["Themes"], "responses": {"200": {"description": "Theme deleted"}}})
@jwt_required()
def delete_theme(theme_id):
    """Delete a custom theme."""
    current_user = get_current_user()
    theme_service.soft_delete_theme(theme_id, organization_id=current_user.organization_id)
    audit_logger.info(f"Theme {theme_id} deleted by user {current_user.id}")
    return success_response(message="Theme deleted")
