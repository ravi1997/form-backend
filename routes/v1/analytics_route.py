"""
Analytics Routes
Provides system-wide statistics for administrators.
"""

from flask import Blueprint, jsonify, current_app, request
from flasgger import swag_from
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Form, FormResponse
from datetime import datetime, timezone
from utils.security import require_roles
from utils.response_helper import success_response, error_response
from logger.unified_logger import app_logger, error_logger

analytics_bp = Blueprint("analytics_bp", __name__)


@analytics_bp.route("/dashboard", methods=["GET"])
@swag_from({
    "tags": [
        "Analytics"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@require_roles("admin", "superadmin", "manager")
def get_dashboard_stats():
    """
    Compute and return system-wide dashboard statistics.
    Restricted to privileged users to prevent sensitive data leakage.
    """
    user_id = get_jwt_identity()
    app_logger.info(f"Fetching dashboard stats for user: {user_id}")
    try:
        total_forms = Form.objects().count()
        published_forms = Form.objects(status="published").count()
        total_responses = FormResponse.objects(is_deleted=False).count()

        # Recent Activity: Last 5 Submissions
        recent_activity = []
        recent_submissions = (
            FormResponse.objects(is_deleted=False)
            .order_by("-submitted_at")
            .limit(5)
        )

        for r in recent_submissions:
            try:
                # Safely handle potentially missing form references
                form_title = r.form.title if r.form else "Unknown/Deleted Form"
                timestamp = (
                    r.submitted_at.isoformat()
                    if r.submitted_at
                    else datetime.now(timezone.utc).isoformat()
                )
                recent_activity.append(
                    {
                        "type": "New Submission",
                        "details": f"Response received for '{form_title}'",
                        "timestamp": timestamp,
                        "id": str(r.id),
                    }
                )
            except Exception as inner_e:
                app_logger.warning(
                    f"Skipping corrupt activity record {r.id}: {inner_e}"
                )
                continue

        app_logger.info(f"Dashboard stats generated successfully for user: {user_id}")
        return success_response(
            data={
                "total_forms": total_forms,
                "active_forms": published_forms,
                "total_responses": total_responses,
                "recent_activity": recent_activity,
            }
        )

    except Exception as e:
        error_logger.error(f"Failed to generate dashboard statistics for user {user_id}: {e}", exc_info=True)
        return error_response(message="Failed to generate analytics", status_code=500)


@analytics_bp.route("/summary", methods=["GET"])
@swag_from({
    "tags": [
        "Analytics"
    ],
    "responses": {
        "200": {
            "description": "Returns organization-wide summary."
        }
    }
})
@require_roles("admin", "superadmin")
def get_summary():
    """Returns organization-wide summary statistics."""
    user_id = get_jwt_identity()
    app_logger.info(f"Fetching analytics summary for user: {user_id}")
    try:
        total_forms = Form.objects().count()
        total_responses = FormResponse.objects(is_deleted=False).count()
        app_logger.info(f"Analytics summary retrieved for user: {user_id}")
        return success_response(data={"total_forms": total_forms, "total_responses": total_responses})
    except Exception as e:
        error_logger.error(f"Error fetching analytics summary for user {user_id}: {e}", exc_info=True)
        return error_response(str(e), status_code=500)


@analytics_bp.route("/trends", methods=["GET"])
@swag_from({
    "tags": [
        "Analytics"
    ],
    "responses": {
        "200": {
            "description": "Returns trends data."
        }
    }
})
@jwt_required()
def get_trends():
    """Returns analytics trends for the organization."""
    user_id = get_jwt_identity()
    app_logger.info(f"Fetching analytics trends for user: {user_id}")
    return success_response(data={"trends": []})
