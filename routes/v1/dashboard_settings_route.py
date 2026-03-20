"""
User Dashboard Settings Routes

Endpoints for managing user dashboard customization:
- GET /api/v1/dashboard/settings - Get user dashboard settings
- PUT /api/v1/dashboard/settings - Update user dashboard settings
- POST /api/v1/dashboard/reset - Reset to default settings
- GET /api/v1/dashboard/widgets - Get available widgets
- POST /api/v1/dashboard/widgets - Add widget to dashboard
- DELETE /api/v1/dashboard/widgets/<widget_id> - Remove widget from dashboard
"""

from flask import Blueprint, request
from flasgger import swag_from
from flask_jwt_extended import get_jwt_identity, jwt_required, get_jwt
from services.dashboard_service import DashboardService
from utils.response_helper import success_response, error_response
import logging

dashboard_settings_bp = Blueprint(
    "dashboard_settings", __name__, url_prefix="/api/v1/dashboard"
)
logger = logging.getLogger(__name__)
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
    try:
        user_id = get_jwt_identity()
        org_id = get_jwt().get("org_id")
        if not org_id:
            return error_response(message="Organization context missing", status_code=400)
            
        settings = dashboard_service.get_user_settings(user_id, org_id)
        return success_response(data=settings.model_dump())
    except Exception as e:
        logger.error(f"Error getting dashboard settings: {e}")
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
    try:
        user_id = get_jwt_identity()
        org_id = get_jwt().get("org_id")
        if not org_id:
            return error_response(message="Organization context missing", status_code=400)
            
        data = request.get_json() or {}
        settings = dashboard_service.update_user_settings(user_id, org_id, data)
        return success_response(data=settings.model_dump(), message="Settings updated")
    except Exception as e:
        logger.error(f"Error updating dashboard settings: {e}")
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
    try:
        user_id = get_jwt_identity()
        org_id = get_jwt().get("org_id")
        if not org_id:
            return error_response(message="Organization missing", status_code=400)
            
        settings = dashboard_service.update_user_settings(user_id, org_id, {
            "theme": "system",
            "language": "en",
            "timezone": "UTC",
            "layout_config": {},
            "favorite_dashboards": []
        })
        return success_response(data=settings.model_dump(), message="Settings reset to defaults")
    except Exception as e:
        logger.error(f"Error resetting settings: {e}")
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
    try:
        widgets = dashboard_service.get_available_widgets()
        return success_response(data=widgets)
    except Exception as e:
        logger.error(f"Error getting widgets: {e}")
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
    try:
        user_id = get_jwt_identity()
        logger.info(
            f"--- Remove Widget branch started for widget_id: {widget_id} (user: {user_id}) ---"
        )
        removed = DashboardService.remove_widget(user_id, widget_id)

        if not removed:
            logger.warning(
                f"Remove widget failed: Widget {widget_id} not found for user: {user_id}"
            )
            return jsonify({"success": False, "error": "Widget not found"}), 404

        logger.info(f"Widget {widget_id} removed successfully for user: {user_id}")
        return jsonify({"success": True, "message": "Widget removed successfully"}), 200

    except Exception as e:
        logger.error(f"Error removing widget: {e}")
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
    try:
        user_id = get_jwt_identity()
        logger.info(
            f"--- Update Widget branch started for widget_id: {widget_id} (user: {user_id}) ---"
        )
        data = request.get_json()

        if not data:
            logger.warning(
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
            logger.warning(
                f"Update widget failed: Widget {widget_id} not found for user: {user_id}"
            )
            return jsonify({"success": False, "error": "Widget not found"}), 404

        logger.info(f"Widget {widget_id} updated successfully for user: {user_id}")
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
        logger.error(f"Error updating widget: {e}")
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
    try:
        user_id = get_jwt_identity()
        logger.info(
            f"--- Update Widget Positions branch started for user: {user_id} ---"
        )
        data = request.get_json()

        if not data or "positions" not in data:
            logger.warning(
                f"Update positions failed: Missing data or 'positions' key for user: {user_id}"
            )
            return (
                jsonify({"success": False, "error": "Positions data is required"}),
                400,
            )

        positions = data["positions"]

        if not isinstance(positions, dict):
            logger.warning(
                f"Update positions failed: 'positions' is not a dictionary for user: {user_id}"
            )
            return (
                jsonify({"success": False, "error": "Positions must be a dictionary"}),
                400,
            )

        updated = DashboardService.update_widget_positions(user_id, positions)

        logger.info(
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
        logger.error(f"Error updating widget positions: {e}")
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
    try:
        user_id = get_jwt_identity()
        logger.info(f"--- Update Layout branch started for user: {user_id} ---")
        data = request.get_json()

        if not data:
            logger.warning(
                f"Update layout failed: Missing request body for user: {user_id}"
            )
            return jsonify({"success": False, "error": "Request body is required"}), 400

        # Validate layout
        logger.debug(f"Validating layout for user: {user_id}")
        validation_result = DashboardService.validate_settings({"layout": data})
        if not validation_result["valid"]:
            logger.warning(
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
        logger.debug(f"Layout validation successful for user: {user_id}")

        settings = DashboardService.save_settings(
            user_id=user_id, layout=data, validate=False
        )

        logger.info(f"Layout updated successfully for user: {user_id}")
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
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        logger.error(f"Error updating layout: {e}")
        return jsonify({"success": False, "error": "Failed to update layout"}), 500
