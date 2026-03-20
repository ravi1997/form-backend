from mongoengine import Document, StringField, DateTimeField, DictField
import uuid

class PromptTemplate(Document):
    """
    [Phase 9: AI Intelligence Platform]
    A Registry for LLM Prompts mapping input schemas to abstract system prompts.
    """
    id = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = StringField(required=True)
    template_name = StringField(required=True)
    system_prompt = StringField(required=True)
    version = StringField(default="1.0.0")

class AIAuditLog(Document):
    """Tracks token consumption and response violations."""
    id = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = StringField(required=True)
    provider = StringField(required=True)
    request_tokens = StringField() # Int
    response_tokens = StringField()
    status = StringField(required=True) # success, timeout, violation
