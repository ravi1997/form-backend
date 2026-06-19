"""
routes/v1/llm_route.py
LLM configuration and management API routes.
"""

import asyncio

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from logger.unified_logger import app_logger, error_logger, audit_logger
from utils.response_helper import success_response, error_response
from utils.security_helpers import get_current_user
from services.llm_service import LLMService
from services.llm_model_registry_service import LLMModelRegistryService
from services.llm_prompt_template_service import LLMPromptTemplateService
from services.llm_usage_tracking_service import LLMUsageTrackingService
from models.llm_model import LLMChatSession, LLMChatMessage
from services.llm_service import LLMProvider

llm_bp = Blueprint("llm", __name__)

# Initialize services
llm_service = LLMService()
model_registry = LLMModelRegistryService()
template_service = LLMPromptTemplateService()
usage_tracker = LLMUsageTrackingService()


def _run_async(coro):
    return asyncio.run(coro)


@llm_bp.route("/config", methods=["GET"])
@jwt_required()
def get_llm_config():
    """Get LLM configuration for the current user."""
    try:
        current_user = get_current_user()
        organization_id = request.args.get("organization_id")
        
        if organization_id:
            # Verify user has access to this organization
            from services.org_service import OrgService
            org_service = OrgService()
            if not org_service.user_has_access(current_user.id, organization_id):
                return error_response("Access denied to organization", 403)
        
        # Get available models
        models = _run_async(
            model_registry.list_models(
            organization_id=organization_id,
            page=1,
            page_size=100
            )
        )
        
        # Get available templates
        templates = _run_async(
            template_service.list_templates(
            organization_id=organization_id,
            page=1,
            page_size=100
            )
        )
        
        # Get usage stats
        usage_stats = _run_async(
            usage_tracker.get_user_usage(
            user_id=str(current_user.id),
            organization_id=organization_id
            )
        )
        
        config = {
            "models": models.get("models", []),
            "templates": templates.get("templates", []),
            "usage": usage_stats,
            "providers": [
                {"id": "openai", "name": "OpenAI", "enabled": True},
                {"id": "anthropic", "name": "Anthropic", "enabled": True},
                {"id": "ollama", "name": "Ollama", "enabled": True}
            ]
        }
        
        return success_response(config)
        
    except Exception as e:
        error_logger.error(f"Error getting LLM config: {str(e)}", exc_info=True)
        return error_response("Failed to get LLM configuration", 500)


@llm_bp.route("/models", methods=["GET"])
@jwt_required()
def list_models():
    """List available LLM models."""
    try:
        current_user = get_current_user()
        organization_id = request.args.get("organization_id")
        provider = request.args.get("provider")
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 50))
        
        if organization_id:
            # Verify user has access to this organization
            from services.org_service import OrgService
            org_service = OrgService()
            if not org_service.user_has_access(current_user.id, organization_id):
                return error_response("Access denied to organization", 403)
        
        models = _run_async(
            model_registry.list_models(
                provider=provider,
                organization_id=organization_id,
                page=page,
                page_size=page_size,
            )
        )
        
        return success_response(models)
        
    except Exception as e:
        error_logger.error(f"Error listing LLM models: {str(e)}", exc_info=True)
        return error_response("Failed to list models", 500)


@llm_bp.route("/templates", methods=["GET"])
@jwt_required()
def list_templates():
    """List available prompt templates."""
    try:
        current_user = get_current_user()
        organization_id = request.args.get("organization_id")
        category = request.args.get("category")
        provider = request.args.get("provider")
        search = request.args.get("search")
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 50))
        
        if organization_id:
            # Verify user has access to this organization
            from services.org_service import OrgService
            org_service = OrgService()
            if not org_service.user_has_access(current_user.id, organization_id):
                return error_response("Access denied to organization", 403)
        
        templates = _run_async(
            template_service.list_templates(
                category=category,
                provider=provider,
                organization_id=organization_id,
                search=search,
                page=page,
                page_size=page_size,
            )
        )
        
        return success_response(templates)
        
    except Exception as e:
        error_logger.error(f"Error listing templates: {str(e)}", exc_info=True)
        return error_response("Failed to list templates", 500)


@llm_bp.route("/generate-form", methods=["POST"])
@jwt_required()
def generate_form():
    """Generate form structure from natural language description."""
    try:
        current_user = get_current_user()
        data = request.get_json()
        
        if not data or "prompt" not in data:
            return error_response("Prompt is required", 400)
        
        prompt = data["prompt"]
        current_form = data.get("current_form")
        provider = data.get("provider", "openai")
        model_id = data.get("model_id")
        organization_id = data.get("organization_id")
        
        if organization_id:
            # Verify user has access to this organization
            from services.org_service import OrgService
            org_service = OrgService()
            if not org_service.user_has_access(current_user.id, organization_id):
                return error_response("Access denied to organization", 403)
        
        # Generate form structure
        result = _run_async(
            llm_service.generate_form(
            prompt=prompt,
            current_form=current_form,
            provider=LLMProvider(provider),
            user_id=str(current_user.id),
            organization_id=organization_id
            )
        )
        
        audit_logger.info(
            f"AUDIT: User {current_user.id} generated form using LLM prompt: {prompt[:100]}..."
        )
        
        return success_response(result)
        
    except Exception as e:
        error_logger.error(f"Error generating form: {str(e)}", exc_info=True)
        return error_response("Failed to generate form", 500)


@llm_bp.route("/chat/sessions", methods=["POST"])
@jwt_required()
def create_chat_session():
    """Create a new LLM chat session."""
    try:
        current_user = get_current_user()
        data = request.get_json()
        
        title = data.get("title", "New Chat")
        context_type = data.get("context_type", "form_builder")
        context_id = data.get("context_id")
        organization_id = data.get("organization_id")
        
        if organization_id:
            # Verify user has access to this organization
            from services.org_service import OrgService
            org_service = OrgService()
            if not org_service.user_has_access(current_user.id, organization_id):
                return error_response("Access denied to organization", 403)
        
        # Create chat session
        session = LLMChatSession(
            user_id=current_user.id,
            organization_id=organization_id,
            session_id=str(uuid.uuid4()),
            title=title,
            context_type=context_type,
            context_id=context_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        session.save()
        
        audit_logger.info(
            f"AUDIT: User {current_user.id} created LLM chat session: {session.session_id}"
        )
        
        return success_response({
            "session_id": session.session_id,
            "title": session.title,
            "context_type": session.context_type,
            "context_id": session.context_id,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat()
        })
        
    except Exception as e:
        error_logger.error(f"Error creating chat session: {str(e)}", exc_info=True)
        return error_response("Failed to create chat session", 500)


@llm_bp.route("/chat/sessions", methods=["GET"])
@jwt_required()
def list_chat_sessions():
    """List user's LLM chat sessions."""
    try:
        current_user = get_current_user()
        organization_id = request.args.get("organization_id")
        context_type = request.args.get("context_type")
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 20))
        
        if organization_id:
            # Verify user has access to this organization
            from services.org_service import OrgService
            org_service = OrgService()
            if not org_service.user_has_access(current_user.id, organization_id):
                return error_response("Access denied to organization", 403)
        
        # Query chat sessions
        query = LLMChatSession.objects(
            user_id=current_user.id,
            is_deleted=False
        )
        
        if organization_id:
            query = query.filter(organization_id=organization_id)
        
        if context_type:
            query = query.filter(context_type=context_type)
        
        # Apply pagination
        skip = (page - 1) * page_size
        sessions = query.order_by("-updated_at").skip(skip).limit(page_size)
        
        # Build response
        session_list = []
        for session in sessions:
            session_list.append({
                "session_id": session.session_id,
                "title": session.title,
                "context_type": session.context_type,
                "context_id": session.context_id,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "last_message_at": session.last_message_at.isoformat() if session.last_message_at else None
            })
        
        return success_response({
            "sessions": session_list,
            "page": page,
            "page_size": page_size,
            "total": query.count()
        })
        
    except Exception as e:
        error_logger.error(f"Error listing chat sessions: {str(e)}", exc_info=True)
        return error_response("Failed to list chat sessions", 500)


@llm_bp.route("/chat/sessions/<session_id>", methods=["GET"])
@jwt_required()
def get_chat_session(session_id):
    """Get a specific chat session with messages."""
    try:
        current_user = get_current_user()
        
        # Get session
        session = LLMChatSession.objects(
            session_id=session_id,
            user_id=current_user.id,
            is_deleted=False
        ).first()
        
        if not session:
            return error_response("Chat session not found", 404)
        
        # Get messages
        messages = LLMChatMessage.objects(
            session_id=session_id
        ).order_by("timestamp")
        
        message_list = []
        for message in messages:
            message_list.append({
                "role": message.role,
                "content": message.content,
                "message_type": message.message_type,
                "timestamp": message.timestamp.isoformat()
            })
        
        return success_response({
            "session": {
                "session_id": session.session_id,
                "title": session.title,
                "context_type": session.context_type,
                "context_id": session.context_id,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat()
            },
            "messages": message_list
        })
        
    except Exception as e:
        error_logger.error(f"Error getting chat session: {str(e)}", exc_info=True)
        return error_response("Failed to get chat session", 500)


@llm_bp.route("/chat/sessions/<session_id>/messages", methods=["POST"])
@jwt_required()
def send_chat_message(session_id):
    """Send a message in a chat session."""
    try:
        current_user = get_current_user()
        data = request.get_json()
        
        if not data or "message" not in data:
            return error_response("Message is required", 400)
        
        # Get session
        session = LLMChatSession.objects(
            session_id=session_id,
            user_id=current_user.id,
            is_deleted=False
        ).first()
        
        if not session:
            return error_response("Chat session not found", 404)
        
        user_message = data["message"]
        
        # Save user message
        user_chat_message = LLMChatMessage(
            session_id=session_id,
            role="user",
            content=user_message,
            message_type="text",
            timestamp=datetime.utcnow()
        )
        user_chat_message.save()
        
        # Generate AI response
        context = {
            "session_id": session_id,
            "context_type": session.context_type,
            "context_id": session.context_id
        }
        
        if session.context_type == "form_builder" and session.context_id:
            # Load form context
            from models.form import Form
            form = Form.objects(id=session.context_id, is_deleted=False).first()
            if form:
                context["form"] = {
                    "id": str(form.id),
                    "name": form.name,
                    "description": form.description
                }
        
        # Generate response using LLM service
        result = _run_async(
            llm_service.generate_completion(
            prompt=user_message,
            provider=LLMProvider.OPENAI,
            user_id=str(current_user.id),
            organization_id=session.organization_id
            )
        )
        
        # Save AI response
        ai_message = LLMChatMessage(
            session_id=session_id,
            role="assistant",
            content=result.get("content", ""),
            message_type="text",
            timestamp=datetime.utcnow()
        )
        ai_message.save()
        
        # Update session
        session.updated_at = datetime.utcnow()
        session.last_message_at = datetime.utcnow()
        session.save()
        
        return success_response({
            "user_message": {
                "role": "user",
                "content": user_message,
                "timestamp": user_chat_message.timestamp.isoformat()
            },
            "ai_response": {
                "role": "assistant",
                "content": result.get("content", ""),
                "timestamp": ai_message.timestamp.isoformat()
            },
            "usage": result.get("usage", {}),
            "cost": result.get("cost", 0.0)
        })
        
    except Exception as e:
        error_logger.error(f"Error sending chat message: {str(e)}", exc_info=True)
        return error_response("Failed to send message", 500)


@llm_bp.route("/chat/sessions/<session_id>", methods=["DELETE"])
@jwt_required()
def delete_chat_session(session_id):
    """Delete a chat session."""
    try:
        current_user = get_current_user()
        
        # Get session
        session = LLMChatSession.objects(
            session_id=session_id,
            user_id=current_user.id,
            is_deleted=False
        ).first()
        
        if not session:
            return error_response("Chat session not found", 404)
        
        # Soft delete session
        session.is_deleted = True
        session.deleted_at = datetime.utcnow()
        session.save()
        
        # Delete messages
        LLMChatMessage.objects(session_id=session_id).delete()
        
        audit_logger.info(
            f"AUDIT: User {current_user.id} deleted LLM chat session: {session_id}"
        )
        
        return success_response({"message": "Chat session deleted successfully"})
        
    except Exception as e:
        error_logger.error(f"Error deleting chat session: {str(e)}", exc_info=True)
        return error_response("Failed to delete chat session", 500)


@llm_bp.route("/usage", methods=["GET"])
@jwt_required()
def get_usage_stats():
    """Get LLM usage statistics for the current user."""
    try:
        current_user = get_current_user()
        organization_id = request.args.get("organization_id")
        period = request.args.get("period", "month")  # day, week, month, year
        
        if organization_id:
            # Verify user has access to this organization
            from services.org_service import OrgService
            org_service = OrgService()
            if not org_service.user_has_access(current_user.id, organization_id):
                return error_response("Access denied to organization", 403)
        
        usage_stats = _run_async(
            usage_tracker.get_user_usage(
            user_id=str(current_user.id),
            organization_id=organization_id,
            period=period
            )
        )
        
        return success_response(usage_stats)
        
    except Exception as e:
        error_logger.error(f"Error getting usage stats: {str(e)}", exc_info=True)
        return error_response("Failed to get usage statistics", 500)
