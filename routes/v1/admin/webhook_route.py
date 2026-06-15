from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity
from flasgger import swag_from

from logger.unified_logger import app_logger, error_logger
from services.webhook_service import WebhookService
from utils.response_helper import error_response, success_response
from utils.security import require_roles

webhook_admin_bp = Blueprint("webhook_admin", __name__)


@webhook_admin_bp.route("/", methods=["GET"])
@swag_from(
    {
        "tags": ["Webhook Administration"],
        "summary": "List webhooks for a form (Admin and Superadmin)",
        "parameters": [
            {
                "name": "form_id",
                "in": "query",
                "type": "string",
                "required": True,
            }
        ],
    }
)
@require_roles("admin", "superadmin")
def list_webhooks():
    admin_id = get_jwt_identity()
    form_id = request.args.get("form_id")
    if not form_id:
        return error_response("form_id is required", 400)
    app_logger.info(f"Listing webhooks for form {form_id} by admin {admin_id}")
    try:
        data = WebhookService.list_webhooks(form_id, admin_id)
        return success_response(data=data)
    except Exception as exc:
        error_logger.error(
            f"Failed to list webhooks for form {form_id}: {exc}", exc_info=True
        )
        return error_response(message=str(exc), status_code=500)


@webhook_admin_bp.route("/", methods=["POST"])
@swag_from(
    {
        "tags": ["Webhook Administration"],
        "summary": "Create a webhook for a form (Admin and Superadmin)",
    }
)
@require_roles("admin", "superadmin")
def create_webhook():
    admin_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    form_id = data.get("form_id")
    if not form_id:
        return error_response("form_id is required", 400)
    try:
        created = WebhookService.create_webhook(
            form_id=form_id,
            user_id=admin_id,
            created_by=admin_id,
            name=data.get("name"),
            event_type=data.get("event_type"),
            action_config=data.get("action_config") or {},
            custom_script=data.get("custom_script"),
            is_active=data.get("is_active", True),
            order=data.get("order"),
            meta_data=data.get("meta_data") or {},
            description=data.get("description"),
        )
        return success_response(data=created, status_code=201)
    except Exception as exc:
        error_logger.error(
            f"Failed to create webhook for form {form_id}: {exc}", exc_info=True
        )
        return error_response(message=str(exc), status_code=400)


@webhook_admin_bp.route("/<webhook_id>", methods=["DELETE"])
@swag_from(
    {
        "tags": ["Webhook Administration"],
        "summary": "Delete a webhook by ID (Admin and Superadmin)",
        "parameters": [
            {
                "name": "webhook_id",
                "in": "path",
                "type": "string",
                "required": True,
            }
        ],
    }
)
@require_roles("admin", "superadmin")
def delete_webhook(webhook_id):
    admin_id = get_jwt_identity()
    try:
        deleted = WebhookService.delete_webhook(webhook_id, admin_id)
        if not deleted:
            return error_response("Webhook not found", 404)
        return success_response(data={"deleted": True, "webhook_id": webhook_id})
    except Exception as exc:
        error_logger.error(
            f"Failed to delete webhook {webhook_id}: {exc}", exc_info=True
        )
        return error_response(message=str(exc), status_code=400)


@webhook_admin_bp.route("/<webhook_id>/test", methods=["POST"])
@swag_from(
    {
        "tags": ["Webhook Administration"],
        "summary": "Trigger a test for a webhook by ID (Admin and Superadmin)",
    }
)
@require_roles("admin", "superadmin")
def test_webhook(webhook_id):
    admin_id = get_jwt_identity()
    try:
        result = WebhookService.trigger_test(webhook_id, admin_id)
        return success_response(data=result)
    except Exception as exc:
        error_logger.error(
            f"Failed to test webhook {webhook_id}: {exc}", exc_info=True
        )
        return error_response(message=str(exc), status_code=400)


@webhook_admin_bp.route("/<webhook_id>/logs", methods=["GET"])
@swag_from(
    {
        "tags": ["Webhook Administration"],
        "summary": "Fetch logs for a webhook by ID (Admin and Superadmin)",
    }
)
@require_roles("admin", "superadmin")
def get_webhook_logs(webhook_id):
    admin_id = get_jwt_identity()
    limit = request.args.get("limit", 50, type=int)
    try:
        data = WebhookService.get_logs(webhook_id, admin_id, limit=limit)
        return success_response(data=data)
    except Exception as exc:
        error_logger.error(
            f"Failed to fetch webhook logs for {webhook_id}: {exc}", exc_info=True
        )
        return error_response(message=str(exc), status_code=400)
