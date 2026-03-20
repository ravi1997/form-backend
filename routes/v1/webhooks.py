from flask import Blueprint, request, jsonify, current_app
from flasgger import swag_from
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timezone
from services.webhook_service import WebhookService
from utils.security import require_roles
from extensions import limiter
import logging

webhooks_bp = Blueprint("webhooks", __name__)
logger = logging.getLogger(__name__)


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
            return jsonify({"error": "url, webhook_id, form_id, and payload are required"}), 400

        schedule_for = None
        if schedule_for_str:
            try:
                schedule_for = datetime.fromisoformat(schedule_for_str.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": "schedule_for must be a valid ISO-8601 datetime"}), 400

        created_by = get_jwt_identity()
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
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Webhook delivery error: {e}")
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
            "required": true
        }
    ]
})
@jwt_required()
def get_webhook_status(delivery_id: str):
    """View status of a specific delivery."""
    try:
        status = WebhookService.get_webhook_status(delivery_id)
        if not status:
            return jsonify({"error": "Webhook delivery not found"}), 404
        return jsonify(status), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@webhooks_bp.route("/history", methods=["GET"])
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
@webhooks_bp.route("/<delivery_id>/history", methods=["GET"])
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
            "required": true
        }
    ]
})
@require_roles("admin", "superadmin", "manager")
def get_webhook_history(delivery_id=None):
    """View system-wide or specific delivery history. Manager restricted."""
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
        return jsonify(history), 200
    except Exception as e:
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
            "required": true
        }
    ]
})
@require_roles("admin", "superadmin")
def retry_webhook(delivery_id: str):
    """Admin only: Manually retry a failed delivery."""
    try:
        data = request.get_json(silent=True) or {}
        reset_count = data.get("reset_count", False)
        result = WebhookService.retry_webhook(delivery_id, reset_count=reset_count)
        return jsonify(result), 200
    except Exception as e:
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
            "required": true
        }
    ]
})
@require_roles("admin", "superadmin")
def cancel_webhook(delivery_id: str):
    """Admin only: Cancel a pending/retrying delivery."""
    try:
        result = WebhookService.cancel_webhook(delivery_id)
        return jsonify(result), 200
    except Exception as e:
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
    try:
        data = request.get_json(silent=True) or {}
        url = data.get("url")
        payload = data.get("payload")
        if not url or not payload:
            return jsonify({"error": "url and payload are required"}), 400

        created_by = get_jwt_identity()
        result = WebhookService.send_webhook(
            url=url,
            payload=payload,
            webhook_id="test_webhook",
            form_id="test_form",
            created_by=created_by,
            max_retries=3
        )
        return jsonify(result), 200
    except Exception as e:
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
    try:
        url = request.args.get("url")
        status = request.args.get("status")
        limit = min(request.args.get("limit", 100, type=int), 500)
        logs = WebhookService.get_webhook_logs(url=url, status=status, limit=limit)
        return jsonify({"count": len(logs), "logs": logs}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
