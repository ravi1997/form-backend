from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from . import form_bp
from services.hook_service import hook_service
from utils.security_helpers import get_current_user, require_permission
from flasgger import swag_from
from logger.unified_logger import app_logger, error_logger, audit_logger

@form_bp.route("/<form_id>/questions/<question_id>/hooks/trigger", methods=["POST"])
@swag_from({
    "tags": ["Form Hooks"],
    "summary": "Synchronously trigger all hooks for a question",
    "parameters": [
        {"name": "form_id", "in": "path", "type": "string", "required": True},
        {"name": "question_id", "in": "path", "type": "string", "required": True},
        {"name": "body", "in": "body", "schema": {"type": "object"}}
    ],
    "responses": {
        "200": {"description": "Execution results for all hooks"}
    }
})
@jwt_required()
def trigger_question_hooks(form_id, question_id):
    app_logger.info(f"Entering trigger_question_hooks for form {form_id}, question {question_id}")
    current_user = get_current_user()
    payload = request.get_json(silent=True) or {}
    try:
        results = hook_service.trigger_question_hooks(
            form_id=form_id,
            question_id=question_id,
            payload=payload,
            user_id=str(current_user.id),
            organization_id=current_user.organization_id
        )
        audit_logger.info(f"Question hooks triggered for question {question_id} by user {current_user.id}")
        return jsonify({"results": results}), 200
    except Exception as e:
        error_logger.error(f"Trigger question hooks error for {question_id}: {e}")
        return jsonify({"error": str(e)}), 400

@form_bp.route("/<form_id>/sections/<section_id>/hooks/trigger", methods=["POST"])
@swag_from({
    "tags": ["Section Hooks"],
    "summary": "Synchronously trigger all hooks for a section",
    "parameters": [
        {"name": "form_id", "in": "path", "type": "string", "required": True},
        {"name": "section_id", "in": "path", "type": "string", "required": True},
        {"name": "body", "in": "body", "schema": {"type": "object"}}
    ],
    "responses": {
        "200": {"description": "Execution results for all hooks"}
    }
})
@jwt_required()
def trigger_section_hooks(form_id, section_id):
    app_logger.info(f"Entering trigger_section_hooks for form {form_id}, section {section_id}")
    current_user = get_current_user()
    payload = request.get_json(silent=True) or {}
    try:
        results = hook_service.trigger_section_hooks(
            form_id=form_id,
            section_id=section_id,
            payload=payload,
            user_id=str(current_user.id),
            organization_id=current_user.organization_id
        )
        audit_logger.info(f"Section hooks triggered for section {section_id} by user {current_user.id}")
        return jsonify({"results": results}), 200
    except Exception as e:
        error_logger.error(f"Trigger section hooks error for {section_id}: {e}")
        return jsonify({"error": str(e)}), 400

@form_bp.route("/<form_id>/hooks/trigger", methods=["POST"])
@swag_from({
    "tags": ["Form Hooks"],
    "summary": "Synchronously trigger all top-level hooks for a form",
    "parameters": [
        {"name": "form_id", "in": "path", "type": "string", "required": True},
        {"name": "body", "in": "body", "schema": {"type": "object"}}
    ],
    "responses": {
        "200": {"description": "Execution results for all hooks"}
    }
})
@jwt_required()
def trigger_form_hooks(form_id):
    app_logger.info(f"Entering trigger_form_hooks for form {form_id}")
    current_user = get_current_user()
    payload = request.get_json(silent=True) or {}
    try:
        results = hook_service.trigger_form_hooks(
            form_id=form_id,
            payload=payload,
            user_id=str(current_user.id),
            organization_id=current_user.organization_id
        )
        audit_logger.info(f"Form hooks triggered for form {form_id} by user {current_user.id}")
        return jsonify({"results": results}), 200
    except Exception as e:
        error_logger.error(f"Trigger form hooks error for {form_id}: {e}")
        return jsonify({"error": str(e)}), 400

@form_bp.route("/projects/<project_id>/hooks/trigger", methods=["POST"])
@swag_from({
    "tags": ["Project Hooks"],
    "summary": "Synchronously trigger all hooks for a project",
    "parameters": [
        {"name": "project_id", "in": "path", "type": "string", "required": True},
        {"name": "body", "in": "body", "schema": {"type": "object"}}
    ],
    "responses": {
        "200": {"description": "Execution results for all hooks"}
    }
})
@jwt_required()
def trigger_project_hooks(project_id):
    app_logger.info(f"Entering trigger_project_hooks for project {project_id}")
    current_user = get_current_user()
    payload = request.get_json(silent=True) or {}
    try:
        results = hook_service.trigger_project_hooks(
            project_id=project_id,
            payload=payload,
            user_id=str(current_user.id),
            organization_id=current_user.organization_id
        )
        audit_logger.info(f"Project hooks triggered for project {project_id} by user {current_user.id}")
        return jsonify({"results": results}), 200
    except Exception as e:
        error_logger.error(f"Trigger project hooks error for {project_id}: {e}")
        return jsonify({"error": str(e)}), 400

@form_bp.route("/external-hooks/register", methods=["POST"])
@swag_from({
    "tags": ["Form Hooks"],
    "summary": "Register a new external hook for approval",
    "parameters": [
        {"name": "body", "in": "body", "schema": {
            "type": "object",
            "required": ["name", "url"],
            "properties": {
                "name": {"type": "string"},
                "url": {"type": "string"},
                "method": {"type": "string", "default": "POST"},
                "headers": {"type": "object"},
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"}
            }
        }}
    ],
    "responses": {
        "201": {"description": "Hook registered and pending approval"}
    }
})
@jwt_required()
def register_hook():
    app_logger.info("Entering register_hook")
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    try:
        hook = hook_service.register_external_hook(
            data=data,
            user=current_user,
            organization_id=current_user.organization_id
        )
        audit_logger.info(f"External hook {hook.id} registered by user {current_user.id}")
        return jsonify({"message": "Hook registered and pending approval", "hook_id": str(hook.id)}), 201
    except Exception as e:
        error_logger.error(f"Register hook error: {e}")
        return jsonify({"error": str(e)}), 400

@form_bp.route("/external-hooks/<hook_id>/approve", methods=["POST"])
@swag_from({
    "tags": ["Form Hooks"],
    "summary": "Approve or reject a registered external hook (Admin only)",
    "parameters": [
        {"name": "hook_id", "in": "path", "type": "string", "required": True},
        {"name": "body", "in": "body", "schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["approved", "rejected"]}
            }
        }}
    ],
    "responses": {
        "200": {"description": "Hook status updated"}
    }
})
@jwt_required()
@require_permission("form", "approve_hooks")
def approve_hook(hook_id):
    app_logger.info(f"Entering approve_hook for ID {hook_id}")
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    status = data.get("status", "approved")
    try:
        hook = hook_service.approve_hook(
            hook_id=hook_id,
            admin=current_user,
            status=status
        )
        audit_logger.info(f"Hook {hook_id} {status} by admin {current_user.id}")
        return jsonify({"message": f"Hook {status}", "hook_id": str(hook.id)}), 200
    except Exception as e:
        error_logger.error(f"Approve hook error for {hook_id}: {e}")
        return jsonify({"error": str(e)}), 400
