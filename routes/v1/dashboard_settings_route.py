from flask import Blueprint, request
from flasgger import swag_from
from flask_jwt_extended import get_jwt_identity, jwt_required, get_jwt
from services.dashboard_service import DashboardService
from utils.response_helper import success_response, error_response
from logger.unified_logger import app_logger, error_logger, audit_logger

dashboard_settings_bp = Blueprint(
    "dashboard_settings", __name__
)
dashboard_service = DashboardService()


# ==================== Settings Endpoints ====================


@dashboard_settings_bp.route("/settings", methods=["GET"])
@swag_from({
    "tags": [
        "Dashboard_Settings"
    ],
    "responses": {
        "200": {
            "description": "Get user dashboard settings."
        }
    }
})
@jwt_required()
def get_dashboard_settings():
    """Get user dashboard settings."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(f"User {user_id} fetching dashboard settings for org {org_id}")

    if not org_id:
        app_logger.warning(f"Get dashboard settings failed for user {user_id}: Organization context missing")
        return error_response(message="Organization context missing", status_code=400)
        
    settings = dashboard_service.get_user_settings(user_id, org_id)
    app_logger.info(f"Dashboard settings retrieved successfully for user {user_id}")
    return success_response(data=settings.model_dump())


@dashboard_settings_bp.route("/settings", methods=["PUT"])
@swag_from({
    "tags": [
        "Dashboard_Settings"
    ],
    "responses": {
        "200": {
            "description": "Update user dashboard settings."
        }
    }
})
@jwt_required()
def update_dashboard_settings():
    """Update user dashboard settings."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(f"User {user_id} updating dashboard settings for org {org_id}")

    if not org_id:
        app_logger.warning(f"Update dashboard settings failed for user {user_id}: Organization context missing")
        return error_response(message="Organization context missing", status_code=400)
        
    data = request.get_json() or {}
    settings = dashboard_service.update_user_settings(user_id, org_id, data)
    
    audit_logger.info(f"User {user_id} updated dashboard settings for org {org_id}")
    app_logger.info(f"Dashboard settings updated successfully for user {user_id}")
    return success_response(data=settings.model_dump(), message="Settings updated")


@dashboard_settings_bp.route("/reset", methods=["POST"])
@swag_from({
    "tags": [
        "Dashboard_Settings"
    ],
    "responses": {
        "200": {
            "description": "Reset user dashboard settings to defaults."
        }
    }
})
@jwt_required()
def reset_dashboard_settings():
    """Reset user dashboard settings to defaults."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(f"User {user_id} resetting dashboard settings for org {org_id}")

    if not org_id:
        app_logger.warning(f"Reset dashboard settings failed for user {user_id}: Organization missing")
        return error_response(message="Organization missing", status_code=400)
        
    settings = dashboard_service.update_user_settings(user_id, org_id, {
        "theme": "system",
        "language": "en",
        "timezone": "UTC",
        "layout_config": {},
        "favorite_dashboards": []
    })
    
    audit_logger.info(f"User {user_id} reset dashboard settings for org {org_id}")
    app_logger.info(f"Dashboard settings reset successfully for user {user_id}")
    return success_response(data=settings.model_dump(), message="Settings reset to defaults")


# ==================== Widget Endpoints ====================


@dashboard_settings_bp.route("/widgets", methods=["GET"])
@swag_from({
    "tags": [
        "Dashboard_Settings"
    ],
    "responses": {
        "200": {
            "description": "Get list of available widget types."
        }
    }
})
@jwt_required()
def get_available_widgets():
    """Get list of available widget types."""
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} fetching available widgets")
    widgets = dashboard_service.get_available_widgets()
    return success_response(data=widgets)


@dashboard_settings_bp.route("/widgets", methods=["POST"])
@swag_from({
    "tags": [
        "Dashboard_Settings"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@jwt_required()
def add_widget():
    user_id = get_jwt_identity()
    app_logger.warning(f"User {user_id} attempted to use deprecated add_widget route")
    return error_response(message="Direct widget addition is deprecated. Update Dashboard instead.", status_code=405)


@dashboard_settings_bp.route("/widgets/<widget_id>", methods=["DELETE"])
@swag_from({
    "tags": [
        "Dashboard_Settings"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "widget_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def remove_widget(widget_id):
    """Remove a widget from the user's dashboard."""
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} removing widget {widget_id}")
    removed = DashboardService.remove_widget(user_id, widget_id)

    if not removed:
        app_logger.warning(
            f"Remove widget failed: Widget {widget_id} not found for user: {user_id}"
        )
        return error_response(message="Widget not found", status_code=404)

    audit_logger.info(f"User {user_id} removed widget {widget_id}")
    app_logger.info(f"Widget {widget_id} removed successfully for user: {user_id}")
    return success_response(message="Widget removed successfully")


@dashboard_settings_bp.route("/widgets/<widget_id>", methods=["PUT"])
@swag_from({
    "tags": [
        "Dashboard_Settings"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "widget_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def update_widget(widget_id):
    """Update a widget's configuration."""
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} updating widget {widget_id}")
    data = request.get_json()

    if not data:
        app_logger.warning(
            f"Update widget failed: Missing request body for user: {user_id}"
        )
        return error_response(message="Request body is required", status_code=400)

    widget = DashboardService.update_widget(
        user_id=user_id,
        widget_id=widget_id,
        position=data.get("position"),
        size=data.get("size"),
        config=data.get("config"),
        is_visible=data.get("is_visible"),
    )

    if not widget:
        app_logger.warning(
            f"Update widget failed: Widget {widget_id} not found for user: {user_id}"
        )
        return error_response(message="Widget not found", status_code=404)

    audit_logger.info(f"User {user_id} updated widget {widget_id} configuration")
    app_logger.info(f"Widget {widget_id} updated successfully for user: {user_id}")
    return success_response(data={"widget": widget}, message="Widget updated successfully")


@dashboard_settings_bp.route("/widgets/positions", methods=["PUT"])
@swag_from({
    "tags": [
        "Dashboard_Settings"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@jwt_required()
def update_widget_positions():
    """Update positions for multiple widgets."""
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} updating multiple widget positions")
    data = request.get_json()

    if not data or "positions" not in data:
        app_logger.warning(
            f"Update positions failed: Missing data or 'positions' key for user: {user_id}"
        )
        return error_response(message="Positions data is required", status_code=400)

    positions = data["positions"]

    if not isinstance(positions, dict):
        app_logger.warning(
            f"Update positions failed: 'positions' is not a dictionary for user: {user_id}"
        )
        return error_response(message="Positions must be a dictionary", status_code=400)

    updated = DashboardService.update_widget_positions(user_id, positions)

    audit_logger.info(f"User {user_id} updated positions for {len(updated)} widgets")
    app_logger.info(
        f"Successfully updated positions for {len(updated)} widgets (user: {user_id})"
    )
    return success_response(data={"updated_widgets": updated}, message=f"Updated positions for {len(updated)} widgets")


@dashboard_settings_bp.route("/layout", methods=["PUT"])
@swag_from({
    "tags": [
        "Dashboard_Settings"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@jwt_required()
def update_layout():
    """Update only the layout configuration."""
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} updating layout configuration")
    data = request.get_json()

    if not data:
        app_logger.warning(
            f"Update layout failed: Missing request body for user: {user_id}"
        )
        return error_response(message="Request body is required", status_code=400)

    # Validate layout
    app_logger.debug(f"Validating layout for user: {user_id}")
    validation_result = DashboardService.validate_settings({"layout": data})
    if not validation_result["valid"]:
        app_logger.warning(
            f"Layout validation failed for user: {user_id}: {validation_result['errors']}"
        )
        return error_response(message="Validation failed", details=validation_result["errors"], status_code=400)
    app_logger.debug(f"Layout validation successful for user: {user_id}")

    settings = DashboardService.save_settings(
        user_id=user_id, layout=data, validate=False
    )

    audit_logger.info(f"User {user_id} updated dashboard layout")
    app_logger.info(f"Layout updated successfully for user: {user_id}")
    return success_response(data={"settings": settings.to_dict()}, message="Layout updated")
