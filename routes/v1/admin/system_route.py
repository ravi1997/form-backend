from flask import Blueprint, jsonify
from flasgger import swag_from
from flask_jwt_extended import jwt_required
from utils.security import require_roles
from services.event_bus import event_bus
from services.analytics_stream_service import analytics_stream_service
from utils.response_helper import success_response

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
    metrics = event_bus.get_metrics()
    return success_response(data=metrics)

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
            "required": true
        }
    ]
})
@jwt_required()
@require_roles("admin", "superadmin")
def get_analytics_trends(org_id):
    """
    Returns submission trends from the OLAP engine.
    """
    trends = analytics_stream_service.get_submission_trends(org_id)
    return success_response(data=trends)
