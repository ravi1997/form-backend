"""
services/form_builder_assistant_service.py
Service for AI-powered form building assistance with chat interface.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid
import json

from logger.unified_logger import app_logger, error_logger
from models.llm_model import LLMChatSession, LLMChatMessage
from services.llm_service import LLMService
from services.llm_prompt_template_service import LLMPromptTemplateService
from services.llm_usage_tracking_service import LLMUsageTrackingService
from utils.exceptions import ValidationError, NotFoundError


class FormBuilderAssistantService:
    """Service for AI-powered form building assistance."""

    def __init__(self):
        self.llm_service = LLMService()
        self.template_service = LLMPromptTemplateService()
        self.usage_tracker = LLMUsageTrackingService()

    async def create_chat_session(
        self,
        user_id: str,
        organization_id: str,
        title: str = "New Chat",
        context_type: str = "form_builder",
        context_id: str = None
    ) -> LLMChatSession:
        """Create a new chat session for form builder assistance."""
        try:
            app_logger.info(f"Creating chat session for user {user_id}")
            
            session_id = str(uuid.uuid4())
            
            session = LLMChatSession(
                user_id=user_id,
                organization_id=organization_id,
                session_id=session_id,
                title=title,
                context_type=context_type,
                context_id=context_id,
                messages=[],
                metadata={},
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            session.save()
            
            # Add system message
            system_message = {
                "role": "system",
                "content": "I'm your AI form building assistant. I can help you create, modify, and improve forms. What would you like to work on today?",
                "message_type": "system",
                "metadata": {}
            }
            
            await self.add_message(session_id, system_message)
            
            app_logger.info(f"Successfully created chat session: {session_id}")
            return session
            
        except Exception as e:
            error_logger.error(f"Failed to create chat session: {str(e)}", exc_info=True)
            raise

    async def get_chat_session(self, session_id: str) -> Dict[str, Any]:
        """Get a chat session by ID."""
        try:
            session = LLMChatSession.objects(
                session_id=session_id,
                is_deleted=False
            ).first()
            
            if not session:
                raise NotFoundError(f"Chat session not found: {session_id}")
            
            # Get messages for this session
            messages = LLMChatMessage.objects(
                session_id=session_id
            ).order_by("timestamp")
            
            message_list = []
            for message in messages:
                message_data = {
                    "id": str(message.id),
                    "role": message.role,
                    "content": message.content,
                    "message_type": message.message_type,
                    "metadata": message.metadata,
                    "timestamp": message.timestamp.isoformat()
                }
                message_list.append(message_data)
            
            return {
                "id": str(session.id),
                "session_id": session.session_id,
                "title": session.title,
                "context_type": session.context_type,
                "context_id": session.context_id,
                "messages": message_list,
                "metadata": session.metadata,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "last_message_at": session.last_message_at.isoformat() if session.last_message_at else None
            }
            
        except Exception as e:
            error_logger.error(f"Failed to get chat session: {str(e)}", exc_info=True)
            raise

    async def list_chat_sessions(
        self,
        user_id: str,
        organization_id: str,
        context_type: str = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """List chat sessions for a user."""
        try:
            query = LLMChatSession.objects(
                user_id=user_id,
                organization_id=organization_id,
                is_deleted=False
            )
            
            if context_type:
                query = query.filter(context_type=context_type)
            
            sessions = query.order_by("-last_message_at").limit(limit)
            
            session_list = []
            for session in sessions:
                session_data = {
                    "id": str(session.id),
                    "session_id": session.session_id,
                    "title": session.title,
                    "context_type": session.context_type,
                    "context_id": session.context_id,
                    "message_count": len(session.messages),
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "last_message_at": session.last_message_at.isoformat() if session.last_message_at else None
                }
                session_list.append(session_data)
            
            return session_list
            
        except Exception as e:
            error_logger.error(f"Failed to list chat sessions: {str(e)}", exc_info=True)
            raise

    async def send_message(
        self,
        session_id: str,
        content: str,
        message_type: str = "text",
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Send a message to the form builder assistant and get response."""
        try:
            app_logger.info(f"Sending message to session {session_id}")
            
            # Get session
            session = LLMChatSession.objects(
                session_id=session_id,
                is_deleted=False
            ).first()
            
            if not session:
                raise NotFoundError(f"Chat session not found: {session_id}")
            
            # Add user message
            user_message = {
                "role": "user",
                "content": content,
                "message_type": message_type,
                "metadata": metadata or {}
            }
            
            await self.add_message(session_id, user_message)
            
            # Generate AI response
            response = await self._generate_ai_response(session, content, metadata)
            
            # Add AI response
            ai_message = {
                "role": "assistant",
                "content": response.get("content", ""),
                "message_type": response.get("message_type", "text"),
                "metadata": {
                    "provider": response.get("provider", ""),
                    "model": response.get("model", ""),
                    "usage": response.get("usage", {}),
                    "cost": response.get("cost", 0.0),
                    **response.get("metadata", {})
                }
            }
            
            await self.add_message(session_id, ai_message)
            
            # Update session
            session.title = self._generate_session_title(content)
            session.last_message_at = datetime.utcnow()
            session.updated_at = datetime.utcnow()
            session.save()
            
            # Return updated session
            return await self.get_chat_session(session_id)
            
        except Exception as e:
            error_logger.error(f"Failed to send message: {str(e)}", exc_info=True)
            raise

    async def _generate_ai_response(
        self,
        session: LLMChatSession,
        user_message: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Generate AI response based on user message and session context."""
        try:
            # Build context from session
            context_messages = []
            recent_messages = LLMChatMessage.objects(
                session_id=session.session_id
            ).order_by("-timestamp").limit(10)  # Last 10 messages
            
            for message in reversed(recent_messages):
                context_messages.append({
                    "role": message.role,
                    "content": message.content
                })
            
            # Determine the type of request
            request_type = self._classify_request(user_message)
            
            if request_type == "form_generation":
                return await self._handle_form_generation(session, user_message, metadata)
            elif request_type == "form_suggestion":
                return await self._handle_form_suggestion(session, user_message, metadata)
            elif request_type == "field_suggestion":
                return await self._handle_field_suggestion(session, user_message, metadata)
            elif request_type == "form_analysis":
                return await self._handle_form_analysis(session, user_message, metadata)
            else:
                # General conversation
                return await self._handle_general_conversation(session, user_message, metadata)
                
        except Exception as e:
            error_logger.error(f"Failed to generate AI response: {str(e)}", exc_info=True)
            return {
                "content": "I'm sorry, I encountered an error while processing your request. Please try again.",
                "message_type": "text",
                "metadata": {"error": str(e)}
            }

    async def _handle_form_generation(
        self,
        session: LLMChatSession,
        user_message: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Handle form generation requests."""
        try:
            # Get current form if available
            current_form = metadata.get("current_form", {}) if metadata else {}
            
            # Use LLM service to generate form
            result = await self.llm_service.generate_form(
                prompt=user_message,
                current_form=current_form,
                user_id=str(session.user_id),
                organization_id=str(session.organization_id)
            )
            
            return {
                "content": json.dumps(result.get("form_structure", {}), indent=2),
                "message_type": "form_generation",
                "provider": result.get("provider"),
                "model": result.get("model"),
                "usage": result.get("usage"),
                "cost": result.get("cost"),
                "metadata": {
                    "original_prompt": user_message,
                    "form_structure": result.get("form_structure", {})
                }
            }
            
        except Exception as e:
            error_logger.error(f"Failed to handle form generation: {str(e)}", exc_info=True)
            raise

    async def _handle_form_suggestion(
        self,
        session: LLMChatSession,
        user_message: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Handle form improvement suggestions."""
        try:
            # Get current form
            current_form = metadata.get("current_form", {}) if metadata else {}
            
            if not current_form:
                return {
                    "content": "I need to see your current form structure to provide suggestions. Please share your form.",
                    "message_type": "text",
                    "metadata": {}
                }
            
            # Get form suggestions
            result = await self.llm_service.get_form_suggestions(
                current_form=current_form,
                user_id=str(session.user_id),
                organization_id=str(session.organization_id)
            )
            
            return {
                "content": result.get("suggestions", ""),
                "message_type": "form_suggestions",
                "provider": result.get("provider"),
                "model": result.get("model"),
                "usage": result.get("usage"),
                "cost": result.get("cost"),
                "metadata": {
                    "current_form": current_form
                }
            }
            
        except Exception as e:
            error_logger.error(f"Failed to handle form suggestions: {str(e)}", exc_info=True)
            raise

    async def _handle_field_suggestion(
        self,
        session: LLMChatSession,
        user_message: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Handle field-specific suggestions."""
        try:
            # Extract field context from message
            field_context = self._extract_field_context(user_message, metadata)
            
            # Use template for field suggestions
            template = await self.template_service.get_template("form_field_suggestions")
            
            if not template:
                # Fallback to general response
                return {
                    "content": "I'd be happy to help you with field suggestions! Could you provide more details about the type of field you're working with?",
                    "message_type": "text",
                    "metadata": {}
                }
            
            # Apply template
            prompt = await self.template_service.apply_template(
                template,
                user_message,
                field_context
            )
            
            # Generate completion
            result = await self.llm_service.generate_completion(
                prompt=prompt,
                user_id=str(session.user_id),
                organization_id=str(session.organization_id)
            )
            
            return {
                "content": result.get("content", ""),
                "message_type": "field_suggestion",
                "provider": result.get("provider"),
                "model": result.get("model"),
                "usage": result.get("usage"),
                "cost": result.get("cost"),
                "metadata": {
                    "field_context": field_context
                }
            }
            
        except Exception as e:
            error_logger.error(f"Failed to handle field suggestion: {str(e)}", exc_info=True)
            raise

    async def _handle_form_analysis(
        self,
        session: LLMChatSession,
        user_message: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Handle form analysis requests."""
        try:
            # Get form responses if available
            responses = metadata.get("responses", []) if metadata else []
            
            if not responses:
                return {
                    "content": "I need form response data to provide analysis. Please share the responses you'd like me to analyze.",
                    "message_type": "text",
                    "metadata": {}
                }
            
            # Analyze responses
            result = await self.llm_service.analyze_form_responses(
                responses=responses,
                analysis_prompt=user_message,
                user_id=str(session.user_id),
                organization_id=str(session.organization_id)
            )
            
            return {
                "content": result.get("analysis", ""),
                "message_type": "form_analysis",
                "provider": result.get("provider"),
                "model": result.get("model"),
                "usage": result.get("usage"),
                "cost": result.get("cost"),
                "metadata": {
                    "responses_count": result.get("responses_count", 0)
                }
            }
            
        except Exception as e:
            error_logger.error(f"Failed to handle form analysis: {str(e)}", exc_info=True)
            raise

    async def _handle_general_conversation(
        self,
        session: LLMChatSession,
        user_message: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Handle general conversation."""
        try:
            # Use general conversation template
            template = await self.template_service.get_template("general_conversation")
            
            if not template:
                # Simple fallback
                return {
                    "content": "I'm here to help you with form building! You can ask me to:\n• Create new forms from descriptions\n• Suggest improvements to existing forms\n• Analyze form responses\n• Recommend field types and configurations\n\nWhat would you like to work on?",
                    "message_type": "text",
                    "metadata": {}
                }
            
            # Apply template
            prompt = await self.template_service.apply_template(
                template,
                user_message,
                metadata or {}
            )
            
            # Generate completion
            result = await self.llm_service.generate_completion(
                prompt=prompt,
                user_id=str(session.user_id),
                organization_id=str(session.organization_id)
            )
            
            return {
                "content": result.get("content", ""),
                "message_type": "text",
                "provider": result.get("provider"),
                "model": result.get("model"),
                "usage": result.get("usage"),
                "cost": result.get("cost"),
                "metadata": {}
            }
            
        except Exception as e:
            error_logger.error(f"Failed to handle general conversation: {str(e)}", exc_info=True)
            raise

    async def add_message(self, session_id: str, message_data: Dict[str, Any]) -> LLMChatMessage:
        """Add a message to a chat session."""
        try:
            message = LLMChatMessage(
                session_id=session_id,
                role=message_data.get("role", "user"),
                content=message_data.get("content", ""),
                message_type=message_data.get("message_type", "text"),
                metadata=message_data.get("metadata", {}),
                timestamp=datetime.utcnow()
            )
            message.save()
            
            # Record template usage if applicable
            if message_data.get("metadata", {}).get("template_id"):
                await self.template_service.record_template_usage(
                    message_data["metadata"]["template_id"]
                )
            
            return message
            
        except Exception as e:
            error_logger.error(f"Failed to add message: {str(e)}", exc_info=True)
            raise

    async def delete_chat_session(self, session_id: str, deleted_by: str = None) -> bool:
        """Delete a chat session (soft delete)."""
        try:
            session = LLMChatSession.objects(
                session_id=session_id,
                is_deleted=False
            ).first()
            
            if not session:
                raise NotFoundError(f"Chat session not found: {session_id}")
            
            # Soft delete session
            session.is_deleted = True
            session.deleted_by = deleted_by
            session.deleted_at = datetime.utcnow()
            session.save()
            
            # Delete associated messages
            LLMChatMessage.objects(session_id=session_id).delete()
            
            app_logger.info(f"Successfully deleted chat session: {session_id}")
            return True
            
        except Exception as e:
            error_logger.error(f"Failed to delete chat session: {str(e)}", exc_info=True)
            raise

    def _classify_request(self, message: str) -> str:
        """Classify the type of user request."""
        message_lower = message.lower()
        
        # Check for form generation keywords
        if any(keyword in message_lower for keyword in [
            "create", "generate", "build", "make", "new form", "start from scratch"
        ]):
            return "form_generation"
        
        # Check for form improvement keywords
        if any(keyword in message_lower for keyword in [
            "improve", "suggest", "better", "enhance", "optimize", "recommendation"
        ]):
            return "form_suggestion"
        
        # Check for field-specific keywords
        if any(keyword in message_lower for keyword in [
            "field", "question", "input", "dropdown", "checkbox", "radio"
        ]):
            return "field_suggestion"
        
        # Check for analysis keywords
        if any(keyword in message_lower for keyword in [
            "analyze", "analysis", "insights", "summary", "statistics", "responses"
        ]):
            return "form_analysis"
        
        # Default to general conversation
        return "general"

    def _generate_session_title(self, first_message: str) -> str:
        """Generate a title for the chat session based on first message."""
        # Simple title generation - in production, use LLM for better titles
        words = first_message.split()[:5]
        title = " ".join(words)
        
        if len(title) > 50:
            title = title[:47] + "..."
        
        return title or "New Chat"

    def _extract_field_context(self, message: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Extract field context from message and metadata."""
        context = {
            "message": message,
            "current_field": metadata.get("current_field", {}) if metadata else {},
            "form_section": metadata.get("form_section", {}) if metadata else {},
            "sibling_fields": metadata.get("sibling_fields", []) if metadata else []
        }
        
        return context

    async def get_form_templates(self) -> List[Dict[str, Any]]:
        """Get available form templates for the assistant."""
        try:
            templates = await self.template_service.list_templates(
                category="form_generation",
                is_public=True
            )
            
            return templates.get("templates", [])
            
        except Exception as e:
            error_logger.error(f"Failed to get form templates: {str(e)}", exc_info=True)
            return []