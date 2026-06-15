import os

import requests
from flask import Blueprint, jsonify, request, g
from flasgger import swag_from
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import User
from services.external_sms_service import get_sms_service
from services.notification_service import NotificationService
from logger.unified_logger import app_logger
from middleware.api_key_auth import require_api_key_or_jwt
from utils.response_helper import error_response, success_response

external_api_bp = Blueprint("external_api", __name__)


@external_api_bp.route("/uhid/<string:uhid>", methods=["GET"])
@swag_from(
    {
        "tags": ["External_Api"],
        "responses": {"200": {"description": "Success"}},
        "parameters": [
            {"name": "uhid", "in": "path", "type": "string", "required": True}
        ],
    }
)
@require_api_key_or_jwt
def get_uhid_details(uhid):
    """Fetch details of a UHID from an upstream service if configured."""
    user_id = getattr(g, "request_identity", None) or get_jwt_identity()
    app_logger.info(f"User {user_id} requested UHID details for: {uhid}")
    base_url = (
        os.getenv("AIIMS_UHID_API_URL")
        or os.getenv("UHID_API_URL")
        or os.getenv("EXTERNAL_UHID_API_URL")
    )
    if not base_url:
        return error_response(
            message="UHID lookup service is not configured", status_code=503
        )

    try:
        response = requests.get(
            f"{base_url.rstrip('/')}/uhid/{uhid}",
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json() if response.content else {}
        return success_response(data=data)
    except requests.RequestException as exc:
        app_logger.warning(f"UHID lookup failed for {uhid}: {exc}")
        return error_response(message="UHID lookup failed", status_code=502)


@external_api_bp.route("/employee/<string:employee_id>", methods=["GET"])
@swag_from(
    {
        "tags": ["External_Api"],
        "responses": {"200": {"description": "Success"}},
        "parameters": [
            {"name": "employee_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@require_api_key_or_jwt
def get_employee_details(employee_id):
    """Fetch employee details from the local user table or an upstream service."""
    user_id = getattr(g, "request_identity", None) or get_jwt_identity()
    app_logger.info(f"User {user_id} requested employee details for: {employee_id}")
    user = User.objects(employee_id=employee_id, is_deleted=False).first()
    if user:
        return success_response(
            data={
                "employee_id": user.employee_id,
                "username": user.username,
                "email": user.email,
                "department": user.department,
                "roles": user.roles or [],
                "organization_id": user.organization_id,
            }
        )

    base_url = (
        os.getenv("AIIMS_EMPLOYEE_API_URL")
        or os.getenv("EMPLOYEE_API_URL")
        or os.getenv("EXTERNAL_EMPLOYEE_API_URL")
    )
    if not base_url:
        return error_response(
            message="Employee lookup service is not configured", status_code=404
        )

    try:
        response = requests.get(
            f"{base_url.rstrip('/')}/employee/{employee_id}",
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json() if response.content else {}
        return success_response(data=data)
    except requests.RequestException:
        return error_response(message="Employee not found", status_code=404)


@external_api_bp.route("/mail", methods=["POST"])
@swag_from({"tags": ["External_Api"], "responses": {"200": {"description": "Success"}}})
@require_api_key_or_jwt
def send_mail():
    """Send mail through the configured email integration."""
    user_id = getattr(g, "request_identity", None) or get_jwt_identity()
    app_logger.info(f"User {user_id} requested to send mail")
    payload = request.get_json(silent=True) or {}
    config = payload.get("config") or payload
    data = payload.get("data")
    if data is None:
        data = {
            key: value
            for key, value in payload.items()
            if key not in {"config", "data"}
        }

    try:
        response = NotificationService._call_external_api(config, data)
        return success_response(data=response or {})
    except RuntimeError as exc:
        return error_response(message=str(exc), status_code=503)
    except Exception as exc:
        app_logger.warning(f"Mail delivery failed: {exc}")
        return error_response(message="Mail delivery failed", status_code=502)


@external_api_bp.route("/sms", methods=["POST"])
@swag_from({"tags": ["External_Api"], "responses": {"200": {"description": "Success"}}})
@require_api_key_or_jwt
def send_sms():
    """Send SMS through the configured SMS integration."""
    user_id = getattr(g, "request_identity", None) or get_jwt_identity()
    app_logger.info(f"User {user_id} requested to send SMS")
    data = request.get_json(silent=True) or {}
    mobile = (
        data.get("mobile")
        or data.get("phone")
        or data.get("recipient")
        or data.get("to")
    )
    if not mobile:
        return error_response(message="mobile is required", status_code=400)

    sms_service = get_sms_service()
    if data.get("title") or data.get("body"):
        result = sms_service.send_notification(
            str(mobile).strip(),
            data.get("title") or "Notification",
            data.get("body") or data.get("message") or "",
        )
    else:
        message = data.get("message") or data.get("body") or ""
        if not message:
            return error_response(message="message is required", status_code=400)
        result = sms_service.send_sms(str(mobile).strip(), message)

    if result.success:
        return success_response(
            data={
                "message_id": result.message_id,
                "status_code": result.status_code,
            }
        )

    return error_response(
        message=result.error_message or "SMS delivery failed",
        status_code=result.status_code or 502,
    )
