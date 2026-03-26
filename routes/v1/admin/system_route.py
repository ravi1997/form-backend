from flask import Blueprint, jsonify
from flasgger import swag_from
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.security import require_roles
from services.event_bus import event_bus
from services.analytics_stream_service import analytics_stream_service
from utils.response_helper import success_response, error_response
from logger.unified_logger import app_logger, error_logger, audit_logger

system_bp = Blueprint("system_bp", __name__)

@system_bp.route("/event-health", methods=["GET"])
@swag_from({
    "tags": [
        "System"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@jwt_required()
@require_roles("superadmin")
def get_event_health():
    """
    Returns metrics about the health of the internal event system.
    Includes consumer lag, DLQ sizes, and stream lengths.
    """
    admin_id = get_jwt_identity()
    app_logger.info(f"Entering get_event_health by admin: {admin_id}")
    try:
        metrics = event_bus.get_metrics()
        app_logger.info("Exiting get_event_health successfully")
        return success_response(data=metrics)
    except Exception as e:
        error_logger.error(f"Failed to fetch event health metrics: {e}", exc_info=True)
        return error_response(message="Failed to fetch event health metrics", status_code=500)

@system_bp.route("/analytics-trends/<org_id>", methods=["GET"])
@swag_from({
    "tags": [
        "System"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "org_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
@require_roles("admin", "superadmin")
def get_analytics_trends(org_id):
    """
    Returns submission trends from the OLAP engine.
    """
    admin_id = get_jwt_identity()
    app_logger.info(f"Entering get_analytics_trends for org_id: {org_id} by admin: {admin_id}")
    try:
        trends = analytics_stream_service.get_submission_trends(org_id)
        app_logger.info(f"Exiting get_analytics_trends successfully for org_id: {org_id}")
        return success_response(data=trends)
    except Exception as e:
        error_logger.error(f"Failed to fetch analytics trends for org {org_id}: {e}", exc_info=True)
        return error_response(message="Failed to fetch analytics trends", status_code=500)

