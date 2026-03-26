from flask import Blueprint, request, jsonify
from flasgger import swag_from
from flask_jwt_extended import get_jwt_identity, jwt_required, get_jwt
from services.dashboard_service import DashboardService
from utils.response_helper import success_response, error_response
from logger.unified_logger import app_logger, error_logger, audit_logger

dashboard_settings_bp = Blueprint(
    "dashboard_settings", __name__, url_prefix="/api/v1/dashboard"
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
    try:
        if not org_id:
            error_logger.warning(f"Get dashboard settings failed for user {user_id}: Organization context missing")
            return error_response(message="Organization context missing", status_code=400)
            
        settings = dashboard_service.get_user_settings(user_id, org_id)
        app_logger.info(f"Dashboard settings retrieved successfully for user {user_id}")
        return success_response(data=settings.model_dump())
    except Exception as e:
        error_logger.error(f"Error getting dashboard settings for user {user_id}: {e}", exc_info=True)
        return error_response(message="Failed to retrieve settings", status_code=500)


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
    try:
        if not org_id:
            error_logger.warning(f"Update dashboard settings failed for user {user_id}: Organization context missing")
            return error_response(message="Organization context missing", status_code=400)
            
        data = request.get_json() or {}
        settings = dashboard_service.update_user_settings(user_id, org_id, data)
        
        audit_logger.info(f"User {user_id} updated dashboard settings for org {org_id}")
        app_logger.info(f"Dashboard settings updated successfully for user {user_id}")
        return success_response(data=settings.model_dump(), message="Settings updated")
    except Exception as e:
        error_logger.error(f"Error updating dashboard settings for user {user_id}: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


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
    try:
        if not org_id:
            error_logger.warning(f"Reset dashboard settings failed for user {user_id}: Organization missing")
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
    except Exception as e:
        error_logger.error(f"Error resetting settings for user {user_id}: {e}", exc_info=True)
        return error_response(message="Failed to reset settings", status_code=500)


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
    try:
        widgets = dashboard_service.get_available_widgets()
        return success_response(data=widgets)
    except Exception as e:
        error_logger.error(f"Error getting widgets for user {user_id}: {e}", exc_info=True)
        return error_response(message="Failed to retrieve widgets", status_code=500)


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
    # In the new architecture, widgets are part of a Dashboard object.
    # This route is likely for personal dashboard configuration.
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
    """
    Remove a widget from the user's dashboard.

    Args:
        widget_id: ID of the widget to remove

    Returns:
        200: Success message
        404: Widget not found
        401: Unauthorized
    """
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} removing widget {widget_id}")
    try:
        removed = DashboardService.remove_widget(user_id, widget_id)

        if not removed:
            app_logger.warning(
                f"Remove widget failed: Widget {widget_id} not found for user: {user_id}"
            )
            return jsonify({"success": False, "error": "Widget not found"}), 404

        audit_logger.info(f"User {user_id} removed widget {widget_id}")
        app_logger.info(f"Widget {widget_id} removed successfully for user: {user_id}")
        return jsonify({"success": True, "message": "Widget removed successfully"}), 200

    except Exception as e:
        error_logger.error(f"Error removing widget {widget_id} for user {user_id}: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Failed to remove widget"}), 500


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
    """
    Update a widget's configuration.

    Args:
        widget_id: ID of the widget to update

    Request Body:
        {
            "position": {"x": 0, "y": 4},  // Optional new position
            "size": {"w": 2, "h": 2},      // Optional new size
            "config": {...},               // Optional config updates
            "is_visible": True             // Optional visibility
        }

    Returns:
        200: Updated widget object
        404: Widget not found
        401: Unauthorized
    """
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} updating widget {widget_id}")
    try:
        data = request.get_json()

        if not data:
            app_logger.warning(
                f"Update widget failed: Missing request body for user: {user_id}"
            )
            return jsonify({"success": False, "error": "Request body is required"}), 400

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
            return jsonify({"success": False, "error": "Widget not found"}), 404

        audit_logger.info(f"User {user_id} updated widget {widget_id} configuration")
        app_logger.info(f"Widget {widget_id} updated successfully for user: {user_id}")
        return (
            jsonify(
                {
                    "success": True,
                    "message": "Widget updated successfully",
                    "widget": widget,
                }
            ),
            200,
        )

    except Exception as e:
        error_logger.error(f"Error updating widget {widget_id} for user {user_id}: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Failed to update widget"}), 500


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
    """
    Update positions for multiple widgets.

    Used for drag-and-drop reordering of widgets.

    Request Body:
        {
            "positions": {
                "widget_id_1": {"x": 0, "y": 0},
                "widget_id_2": {"x": 2, "y": 0}
            }
        }

    Returns:
        200: List of updated widgets
        400: Validation error
        401: Unauthorized
    """
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} updating multiple widget positions")
    try:
        data = request.get_json()

        if not data or "positions" not in data:
            app_logger.warning(
                f"Update positions failed: Missing data or 'positions' key for user: {user_id}"
            )
            return (
                jsonify({"success": False, "error": "Positions data is required"}),
                400,
            )

        positions = data["positions"]

        if not isinstance(positions, dict):
            app_logger.warning(
                f"Update positions failed: 'positions' is not a dictionary for user: {user_id}"
            )
            return (
                jsonify({"success": False, "error": "Positions must be a dictionary"}),
                400,
            )

        updated = DashboardService.update_widget_positions(user_id, positions)

        audit_logger.info(f"User {user_id} updated positions for {len(updated)} widgets")
        app_logger.info(
            f"Successfully updated positions for {len(updated)} widgets (user: {user_id})"
        )
        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Updated positions for {len(updated)} widgets",
                    "updated_widgets": updated,
                }
            ),
            200,
        )

    except Exception as e:
        error_logger.error(f"Error updating widget positions for user {user_id}: {e}", exc_info=True)
        return (
            jsonify({"success": False, "error": "Failed to update widget positions"}),
            500,
        )


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
    """
    Update only the layout configuration.

    Request Body:
        {
            "columns": 4,
            "rowHeight": 120,
            "margin": [15, 15],
            "compactType": "vertical",
            "positions": {
                "widget_id_1": {"x": 0, "y": 0}
            }
        }

    Returns:
        200: Updated settings object
        400: Validation error
        401: Unauthorized
    """
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} updating layout configuration")
    try:
        data = request.get_json()

        if not data:
            app_logger.warning(
                f"Update layout failed: Missing request body for user: {user_id}"
            )
            return jsonify({"success": False, "error": "Request body is required"}), 400

        # Validate layout
        app_logger.debug(f"Validating layout for user: {user_id}")
        validation_result = DashboardService.validate_settings({"layout": data})
        if not validation_result["valid"]:
            app_logger.warning(
                f"Layout validation failed for user: {user_id}: {validation_result['errors']}"
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Validation failed",
                        "details": validation_result["errors"],
                    }
                ),
                400,
            )
        app_logger.debug(f"Layout validation successful for user: {user_id}")

        settings = DashboardService.save_settings(
            user_id=user_id, layout=data, validate=False
        )

        audit_logger.info(f"User {user_id} updated dashboard layout")
        app_logger.info(f"Layout updated successfully for user: {user_id}")
        return (
            jsonify(
                {
                    "success": True,
                    "message": "Layout updated",
                    "settings": settings.to_dict(),
                }
            ),
            200,
        )

    except ValueError as ve:
        error_logger.warning(f"Validation error updating layout for user {user_id}: {ve}")
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        error_logger.error(f"Error updating layout for user {user_id}: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Failed to update layout"}), 500
