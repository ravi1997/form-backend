from flask import Blueprint, request, jsonify, current_app
from flasgger import swag_from
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timezone
from services.webhook_service import WebhookService
from utils.security import require_roles
from extensions import limiter
from logger.unified_logger import app_logger, error_logger, audit_logger

webhooks_bp = Blueprint("webhooks", __name__)


@webhooks_bp.route("/deliver", methods=["POST"])
@swag_from({
    "tags": [
        "Webhooks"
    ],
    "responses": {
        "200": {
            "description": "Trigger webhook delivery. Restricted to managers and above."
        }
    }
})
@require_roles("admin", "superadmin", "manager")
def deliver_webhook():
    """Trigger webhook delivery. Restricted to managers and above."""
    app_logger.info("Entering deliver_webhook")
    try:
        data = request.get_json(silent=True) or {}
        url = data.get("url")
        webhook_id = data.get("webhook_id")
        form_id = data.get("form_id")
        payload = data.get("payload")
        max_retries = data.get("max_retries", 5)
        headers = data.get("headers")
        timeout = data.get("timeout", 10)
        schedule_for_str = data.get("schedule_for")

        if not url or not webhook_id or not form_id or not payload:
            app_logger.warning(f"Webhook delivery failed: missing required fields. URL: {url}, Webhook ID: {webhook_id}, Form ID: {form_id}")
            return jsonify({"error": "url, webhook_id, form_id, and payload are required"}), 400

        schedule_for = None
        if schedule_for_str:
            try:
                schedule_for = datetime.fromisoformat(schedule_for_str.replace("Z", "+00:00"))
            except ValueError:
                app_logger.warning(f"Webhook delivery failed: invalid schedule_for format: {schedule_for_str}")
                return jsonify({"error": "schedule_for must be a valid ISO-8601 datetime"}), 400

        created_by = get_jwt_identity()
        app_logger.info(f"Triggering webhook delivery for form_id: {form_id}, webhook_id: {webhook_id} by user: {created_by}")
        
        result = WebhookService.send_webhook(
            url=url,
            payload=payload,
            webhook_id=webhook_id,
            form_id=form_id,
            created_by=created_by,
            max_retries=max_retries,
            headers=headers,
            timeout=timeout,
            schedule_for=schedule_for,
        )
        
        audit_logger.info(f"Webhook delivery triggered. Form ID: {form_id}, Webhook ID: {webhook_id}, URL: {url}, User: {created_by}")
        app_logger.info("Exiting deliver_webhook successfully")
        return jsonify(result), 200
    except Exception as e:
        error_logger.error(f"Webhook delivery error: {e}", exc_info=True)
        return jsonify({"error": "Failed to trigger webhook"}), 500


@webhooks_bp.route("/<delivery_id>/status", methods=["GET"])
@swag_from({
    "tags": [
        "Webhooks"
    ],
    "responses": {
        "200": {
            "description": "View status of a specific delivery."
        }
    },
    "parameters": [
        {
            "name": "delivery_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def get_webhook_status(delivery_id: str):
    """View status of a specific delivery."""
    app_logger.info(f"Entering get_webhook_status for delivery_id: {delivery_id}")
    try:
        status = WebhookService.get_webhook_status(delivery_id)
        if not status:
            app_logger.warning(f"Webhook delivery not found: {delivery_id}")
            return jsonify({"error": "Webhook delivery not found"}), 404
        app_logger.info(f"Exiting get_webhook_status for delivery_id: {delivery_id} successfully")
        return jsonify(status), 200
    except Exception as e:
        error_logger.error(f"Error fetching webhook status for {delivery_id}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webhooks_bp.route("/history", methods=["GET"], endpoint="get_webhook_history")
@swag_from({
    "tags": [
        "Webhooks"
    ],
    "responses": {
        "200": {
            "description": "View system-wide or specific delivery history. Manager restricted."
        }
    }
})
@webhooks_bp.route("/<delivery_id>/history", methods=["GET"], endpoint="get_webhook_history_by_id")
@swag_from({
    "tags": [
        "Webhooks"
    ],
    "responses": {
        "200": {
            "description": "View system-wide or specific delivery history. Manager restricted."
        }
    },
    "parameters": [
        {
            "name": "delivery_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@require_roles("admin", "superadmin", "manager")
def get_webhook_history(delivery_id=None):
    """View system-wide or specific delivery history. Manager restricted."""
    app_logger.info(f"Entering get_webhook_history. delivery_id: {delivery_id}")
    try:
        form_id = request.args.get("form_id")
        webhook_id = request.args.get("webhook_id")
        status = request.args.get("status")
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)

        history = WebhookService.get_webhook_history(
            form_id=form_id,
            webhook_id=webhook_id,
            status=status,
            page=page,
            per_page=per_page,
        )
        app_logger.info("Exiting get_webhook_history successfully")
        return jsonify(history), 200
    except Exception as e:
        error_logger.error(f"Error fetching webhook history: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webhooks_bp.route("/<delivery_id>/retry", methods=["POST"])
@swag_from({
    "tags": [
        "Webhooks"
    ],
    "responses": {
        "200": {
            "description": "Admin only: Manually retry a failed delivery."
        }
    },
    "parameters": [
        {
            "name": "delivery_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@require_roles("admin", "superadmin")
def retry_webhook(delivery_id: str):
    """Admin only: Manually retry a failed delivery."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Entering retry_webhook for delivery_id: {delivery_id} by admin: {admin_id}")
    try:
        data = request.get_json(silent=True) or {}
        reset_count = data.get("reset_count", False)
        result = WebhookService.retry_webhook(delivery_id, reset_count=reset_count)
        
        audit_logger.info(f"Webhook delivery retry initiated. Delivery ID: {delivery_id}, Reset Count: {reset_count}, Admin: {admin_id}")
        app_logger.info(f"Exiting retry_webhook for delivery_id: {delivery_id} successfully")
        return jsonify(result), 200
    except Exception as e:
        error_logger.error(f"Error retrying webhook delivery {delivery_id}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webhooks_bp.route("/<delivery_id>/cancel", methods=["DELETE"])
@swag_from({
    "tags": [
        "Webhooks"
    ],
    "responses": {
        "200": {
            "description": "Admin only: Cancel a pending/retrying delivery."
        }
    },
    "parameters": [
        {
            "name": "delivery_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@require_roles("admin", "superadmin")
def cancel_webhook(delivery_id: str):
    """Admin only: Cancel a pending/retrying delivery."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Entering cancel_webhook for delivery_id: {delivery_id} by admin: {admin_id}")
    try:
        result = WebhookService.cancel_webhook(delivery_id)
        
        audit_logger.info(f"Webhook delivery cancelled. Delivery ID: {delivery_id}, Admin: {admin_id}")
        app_logger.info(f"Exiting cancel_webhook for delivery_id: {delivery_id} successfully")
        return jsonify(result), 200
    except Exception as e:
        error_logger.error(f"Error cancelling webhook delivery {delivery_id}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webhooks_bp.route("/test", methods=["POST"])
@swag_from({
    "tags": [
        "Webhooks"
    ],
    "responses": {
        "200": {
            "description": "Admin only: Test webhook delivery to a specific URL."
        }
    }
})
@require_roles("admin", "superadmin")
@limiter.limit("5 per minute")
def test_webhook():
    """Admin only: Test webhook delivery to a specific URL."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Entering test_webhook by admin: {admin_id}")
    try:
        data = request.get_json(silent=True) or {}
        url = data.get("url")
        payload = data.get("payload")
        if not url or not payload:
            app_logger.warning(f"Test webhook failed: missing URL or payload by admin: {admin_id}")
            return jsonify({"error": "url and payload are required"}), 400

        result = WebhookService.send_webhook(
            url=url,
            payload=payload,
            webhook_id="test_webhook",
            form_id="test_form",
            created_by=admin_id,
            max_retries=3
        )
        
        audit_logger.info(f"Test webhook triggered. URL: {url}, Admin: {admin_id}")
        app_logger.info("Exiting test_webhook successfully")
        return jsonify(result), 200
    except Exception as e:
        error_logger.error(f"Error in test_webhook: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webhooks_bp.route("/logs", methods=["GET"])
@swag_from({
    "tags": [
        "Webhooks"
    ],
    "responses": {
        "200": {
            "description": "Admin only: Retrieve low-level delivery logs."
        }
    }
})
@require_roles("admin", "superadmin")
def get_webhook_logs():
    """Admin only: Retrieve low-level delivery logs."""
    app_logger.info("Entering get_webhook_logs")
    try:
        url = request.args.get("url")
        status = request.args.get("status")
        limit = min(request.args.get("limit", 100, type=int), 500)
        logs = WebhookService.get_webhook_logs(url=url, status=status, limit=limit)
        app_logger.info(f"Exiting get_webhook_logs successfully. Count: {len(logs)}")
        return jsonify({"count": len(logs), "logs": logs}), 200
    except Exception as e:
        error_logger.error(f"Error fetching webhook logs: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

