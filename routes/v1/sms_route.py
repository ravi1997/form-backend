"""
SMS Route - External API Wrapper
Provides endpoints for sending SMS, OTPs, and Notifications via AIIMS SMS API.
Protected by JWT and Rate Limiting to prevent resource abuse.
"""

import logging
from flask import Blueprint, request, jsonify
from flasgger import swag_from
from flask_jwt_extended import jwt_required
from services.external_sms_service import get_sms_service
from utils.security import require_roles
from extensions import limiter

logger = logging.getLogger(__name__)

sms_bp = Blueprint("sms", __name__, url_prefix="/api/v1/sms")


@sms_bp.route("/single", methods=["POST"])
@swag_from({
    "tags": [
        "Sms"
    ],
    "responses": {
        "200": {
            "description": "Forward a single SMS request to the external provider."
        }
    }
})
@require_roles("admin", "superadmin", "manager")
@limiter.limit("10 per minute")
def send_single_sms():
    """Forward a single SMS request to the external provider."""
    try:
        data = request.get_json(silent=True) or {}
        mobile = data.get("mobile")
        message = data.get("message")

        if not mobile or not message:
            return jsonify({"error": "mobile and message are required"}), 400

        sms_service = get_sms_service()
        result = sms_service.send_sms(str(mobile).strip(), message)

        if result.success:
            return jsonify({
                "success": True, 
                "message_id": result.message_id, 
                "status_code": result.status_code
            }), 200
            
        return jsonify({
            "success": False, 
            "error": result.error_message, 
            "status_code": result.status_code or 500
        }), result.status_code or 500

    except Exception as e:
        logger.exception(f"SMS delivery error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@sms_bp.route("/otp", methods=["POST"])
@swag_from({
    "tags": [
        "Sms"
    ],
    "responses": {
        "200": {
            "description": "Manually send an OTP. Restrict to admins to prevent spam."
        }
    }
})
@require_roles("admin", "superadmin") # Internal service tool
@limiter.limit("5 per minute")
def send_otp():
    """Manually send an OTP. Restrict to admins to prevent spam."""
    try:
        data = request.get_json(silent=True) or {}
        mobile = data.get("mobile")
        otp = data.get("otp")

        if not mobile or not otp:
            return jsonify({"error": "mobile and otp are required"}), 400

        sms_service = get_sms_service()
        result = sms_service.send_otp(str(mobile).strip(), otp)

        if result.success:
            return jsonify({"success": True, "message_id": result.message_id}), 200
        
        return jsonify({"success": False, "error": result.error_message}), 400

    except Exception as e:
        logger.exception(f"OTP delivery error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@sms_bp.route("/notify", methods=["POST"])
@swag_from({
    "tags": [
        "Sms"
    ],
    "responses": {
        "200": {
            "description": "Send triggered notifications."
        }
    }
})
@require_roles("admin", "superadmin", "manager")
def send_notification():
    """Send triggered notifications."""
    try:
        data = request.get_json(silent=True) or {}
        mobile = data.get("mobile")
        title = data.get("title", "")
        body = data.get("body", "")

        if not mobile or not body:
            return jsonify({"error": "mobile and body are required"}), 400

        sms_service = get_sms_service()
        result = sms_service.send_notification(str(mobile).strip(), title, body)

        if result.success:
            return jsonify({"success": True, "message_id": result.message_id}), 200
        
        return jsonify({"success": False, "error": result.error_message}), 400

    except Exception as e:
        logger.exception(f"Notification delivery error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@sms_bp.route("/health", methods=["GET"])
@swag_from({
    "tags": [
        "Sms"
    ],
    "responses": {
        "200": {
            "description": "Verify SMS provider connectivity."
        }
    }
})
@jwt_required()
def health_check():
    """Verify SMS provider connectivity."""
    try:
        sms_service = get_sms_service()
        if sms_service.api_url and sms_service.api_token:
            return jsonify({"status": "healthy", "service": "external_sms"}), 200
        return jsonify({"status": "unhealthy", "error": "API not configured"}), 503
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 503
