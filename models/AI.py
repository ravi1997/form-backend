from models.base import BaseDocument
from mongoengine import StringField, DateTimeField, DictField
import uuid

class PromptTemplate(BaseDocument):
    """
    [Phase 9: AI Intelligence Platform]
    A Registry for LLM Prompts mapping input schemas to abstract system prompts.
    """
    # BaseDocument already provides id as UUIDField and organization_id
    template_name = StringField(required=True)
    system_prompt = StringField(required=True)
    version = StringField(default="1.0.0")

class AIAuditLog(BaseDocument):
    """Tracks token consumption and response violations."""
    provider = StringField(required=True)
    request_tokens = StringField() # Int
    response_tokens = StringField()
    status = StringField(required=True) # success, timeout, violation
