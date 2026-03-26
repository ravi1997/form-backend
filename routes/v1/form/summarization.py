from . import form_bp
from flasgger import swag_from
"""
Summarization Routes
API endpoints for automated response summarization.
"""

from flask import (
    request,
    jsonify,
    current_app,
    Response,
    stream_with_context,
)
from datetime import datetime, timedelta
import time
import json
from uuid import UUID

from models import Form, FormResponse, SummarySnapshot
from services.summarization_service import SummarizationService
from services.ollama_service import OllamaService
from flask_jwt_extended import jwt_required
from routes.v1.form.helper import get_current_user

@form_bp.route("/<form_id>/summarize", methods=["POST"])
@swag_from({
    "tags": ["Form"],
    "responses": {"200": {"description": "Success"}},
    "parameters": [{"name": "form_id", "in": "path", "type": "string", "required": True}]
})
@jwt_required()
def summarize(form_id: str):
    """Generate summary from form responses."""
    app_logger.info(f"Entering summarize for form_id: {form_id}")
    user = get_current_user()
    data = request.get_json() or {}
    try:
        form_uuid = UUID(form_id)
        form = Form.objects(id=form_uuid, organization_id=user.organization_id).first()
        if not form:
             app_logger.warning(f"Form not found: {form_id}")
             return jsonify({"error": "Form not found", "success": False}), 404
    except ValueError:
        app_logger.warning(f"Invalid form ID format: {form_id}")
        return jsonify({"error": "Invalid form ID format", "success": False}), 400

    response_ids = data.get("response_ids", [])

    try:
        # Check if we have responses
        if response_ids:
            responses_count = FormResponse.objects(id__in=response_ids, form=form_uuid, is_deleted=False).count()
        else:
            responses_count = FormResponse.objects(form=form_uuid, is_deleted=False).count()
        
        if responses_count < 2:
             app_logger.warning(f"Insufficient responses for summarization for form {form_id}: {responses_count}")
             return jsonify({"error": "At least 2 responses required for summarization", "success": False}), 400

        summarizer = SummarizationService()
        # The service might return just the string or a dict, let's wrap it
        summary_text = summarizer.summarize_form(str(form.id), response_ids=response_ids)
        
        app_logger.info(f"Exiting summarize for form_id: {form_id}")
        return jsonify({
            "success": True, 
            "summary": summary_text,
            "form_id": str(form.id)
        }), 200
    except Exception as e:
        error_logger.error(f"Summarization error for form {form_id}: {e}", exc_info=True)
        return jsonify({"error": str(e), "success": False}), 500

@form_bp.route("/<form_id>/summarize-stream", methods=["POST"])
@jwt_required()
def summarize_stream(form_id: str):
    """Generate summary from form responses with streaming response."""
    app_logger.info(f"Entering summarize_stream for form_id: {form_id}")
    user = get_current_user()
    try:
        form_uuid = UUID(form_id)
        form = Form.objects(id=form_uuid, organization_id=user.organization_id).first()
        if not form:
             app_logger.warning(f"Form not found: {form_id}")
             return jsonify({"error": "Form not found", "success": False}), 404
    except ValueError:
        app_logger.warning(f"Invalid form ID format: {form_id}")
        return jsonify({"error": "Invalid form ID format", "success": False}), 400

    data = request.get_json() or {}
    response_ids = data.get("response_ids", [])

    def generate():
        try:
            summarizer = SummarizationService()
            # This is a placeholder for actual streaming logic if the service supports it
            # For now, we'll just return the full summary in chunks
            summary = summarizer.summarize_form(str(form.id), response_ids=response_ids)
            app_logger.info(f"Exiting summarize_stream for form_id: {form_id}")
            yield f"data: {json.dumps({'content': summary, 'done': True})}\n\n"
        except Exception as e:
            error_logger.error(f"Summarization streaming error for form {form_id}: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")
