"""
routes/v1/admin/ai_ops_route.py
Blueprint for administering LoRA model loops and monitoring training state.
"""

import os
import json
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from flasgger import swag_from
from utils.security import require_roles
from utils.response_helper import success_response, error_response
from tasks.ai_tasks import async_run_lora_improvement_loop
from logger.unified_logger import app_logger, error_logger

ai_ops_bp = Blueprint("ai_ops", __name__)

STATE_PATH = "lora/improvement_state.json"

@ai_ops_bp.route("/lora/improve", methods=["POST"])
@swag_from(
    {
        "tags": ["AI Ops"],
        "parameters": [
            {
                "name": "body",
                "in": "body",
                "required": False,
                "schema": {
                    "type": "object",
                    "properties": {
                        "cycles": {"type": "integer", "default": 1},
                        "target_dataset_size": {"type": "integer", "default": 10000},
                        "fast": {"type": "boolean", "default": True}
                    }
                }
            }
        ],
        "responses": {
            "202": {"description": "LoRA improvement loop triggered asynchronously"},
            "401": {"description": "Unauthorized"},
            "403": {"description": "Forbidden"}
        }
    }
)
@require_roles("superadmin")
def trigger_lora_improvement():
    """
    Trigger the LoRA dataset building, validation, and training loop asynchronously.
    """
    app_logger.info("Entering trigger_lora_improvement")
    data = request.get_json() or {}
    cycles = data.get("cycles", 1)
    target_dataset_size = data.get("target_dataset_size", 10000)
    fast = data.get("fast", True)

    try:
        task = async_run_lora_improvement_loop.delay(
            cycles=cycles,
            target_dataset_size=target_dataset_size,
            fast=fast
        )
        return success_response(
            data={"task_id": task.id},
            message="LoRA improvement loop initiated",
            status_code=202
        )
    except Exception as exc:
        error_logger.error(f"Failed to trigger LoRA improvement task: {exc}", exc_info=True)
        return error_response(message="Failed to trigger task", status_code=500)


@ai_ops_bp.route("/lora/status", methods=["GET"])
@swag_from(
    {
        "tags": ["AI Ops"],
        "responses": {
            "200": {"description": "Current LoRA model training and evaluation state retrieved"},
            "401": {"description": "Unauthorized"},
            "403": {"description": "Forbidden"}
        }
    }
)
@require_roles("superadmin")
def get_lora_status():
    """
    Retrieve current pipeline cycles, last execution timing, and performance scores.
    """
    app_logger.info("Entering get_lora_status")
    try:
        state = {}
        if os.path.exists(STATE_PATH):
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                state = json.load(f)
        return success_response(data=state)
    except Exception as exc:
        error_logger.error(f"Failed to read LoRA state: {exc}", exc_info=True)
        return error_response(message="Failed to retrieve status", status_code=500)
