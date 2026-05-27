"""
SMS Route - External API Wrapper
Provides endpoints for sending SMS, OTPs, and Notifications via AIIMS SMS API.
Protected by JWT and Rate Limiting to prevent resource abuse.
"""

from flask import Blueprint, request
from flasgger import swag_from
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.external_sms_service import get_sms_service
from utils.security import require_roles
from extensions import limiter
from logger.unified_logger import app_logger, error_logger, audit_logger
from utils.response_helper import success_response, error_response

sms_bp = Blueprint("sms", __name__)


@sms_bp.route("/single", methods=["POST"])
@swag_from(
    {
        "tags": ["Sms"],
        "responses": {
            "200": {
                "description": "Forward a single SMS request to the external provider."
            }
        },
    }
)
@require_roles("admin", "superadmin", "manager")
@limiter.limit("10 per minute")
def send_single_sms():
    """Forward a single SMS request to the external provider."""
    current_user = get_jwt_identity()
    app_logger.info(f"User {current_user} requesting single SMS delivery")

    data = request.get_json(silent=True) or {}
    mobile = data.get("mobile")
    message = data.get("message")

    if not mobile or not message:
        app_logger.warning(
            f"Single SMS request failed: Missing mobile or message (User: {current_user})"
        )
        return error_response(
            message="mobile and message are required", status_code=400
        )

    sms_service = get_sms_service()
    result = sms_service.send_sms(str(mobile).strip(), message)

    if result.success:
        audit_logger.info(f"SMS sent successfully to {mobile} by user {current_user}")
        return success_response(
            data={"message_id": result.message_id, "status_code": result.status_code}
        )

    error_logger.error(
        f"SMS delivery failed for {mobile}: {result.error_message} (User: {current_user})"
    )
    return error_response(
        message=result.error_message or "Failed to deliver SMS",
        status_code=result.status_code or 500,
    )


@sms_bp.route("/otp", methods=["POST"])
@swag_from(
    {
        "tags": ["Sms"],
        "responses": {
            "200": {
                "description": "Manually send an OTP. Restrict to admins to prevent spam."
            }
        },
    }
)
@require_roles("admin", "superadmin")  # Internal service tool
@limiter.limit("5 per minute")
def send_otp():
    """Manually send an OTP. Restrict to admins to prevent spam."""
    current_user = get_jwt_identity()
    app_logger.info(f"User {current_user} requesting manual OTP delivery")

    data = request.get_json(silent=True) or {}
    mobile = data.get("mobile")
    otp = data.get("otp")

    if not mobile or not otp:
        app_logger.warning(
            f"OTP request failed: Missing mobile or OTP (User: {current_user})"
        )
        return error_response(message="mobile and otp are required", status_code=400)

    sms_service = get_sms_service()
    result = sms_service.send_otp(str(mobile).strip(), otp)

    if result.success:
        audit_logger.info(f"OTP sent successfully to {mobile} by user {current_user}")
        return success_response(data={"message_id": result.message_id})

    error_logger.error(
        f"OTP delivery failed for {mobile}: {result.error_message} (User: {current_user})"
    )
    return error_response(
        message=result.error_message or "Failed to deliver OTP", status_code=400
    )


@sms_bp.route("/notify", methods=["POST"])
@swag_from(
    {
        "tags": ["Sms"],
        "responses": {"200": {"description": "Send triggered notifications."}},
    }
)
@require_roles("admin", "superadmin", "manager")
def send_notification():
    """Send triggered notifications."""
    current_user = get_jwt_identity()
    app_logger.info(f"User {current_user} requesting notification delivery")

    data = request.get_json(silent=True) or {}
    mobile = data.get("mobile")
    title = data.get("title", "")
    body = data.get("body", "")

    if not mobile or not body:
        app_logger.warning(
            f"Notification request failed: Missing mobile or body (User: {current_user})"
        )
        return error_response(message="mobile and body are required", status_code=400)

    sms_service = get_sms_service()
    result = sms_service.send_notification(str(mobile).strip(), title, body)

    if result.success:
        audit_logger.info(
            f"Notification sent successfully to {mobile} by user {current_user}"
        )
        return success_response(data={"message_id": result.message_id})

    error_logger.error(
        f"Notification delivery failed for {mobile}: {result.error_message} (User: {current_user})"
    )
    return error_response(
        message=result.error_message or "Failed to deliver notification",
        status_code=400,
    )


@sms_bp.route("/health", methods=["GET"])
@swag_from(
    {
        "tags": ["Sms"],
        "responses": {"200": {"description": "Verify SMS provider connectivity."}},
    }
)
@jwt_required()
def health_check():
    """Verify SMS provider connectivity."""
    app_logger.info("SMS service health check requested")
    sms_service = get_sms_service()
    if sms_service.api_url and sms_service.api_token:
        app_logger.info("SMS service health check: healthy")
        return success_response(data={"status": "healthy", "service": "external_sms"})

    app_logger.warning("SMS service health check: unhealthy (API not configured)")
    return error_response(message="SMS service not configured", status_code=503)
