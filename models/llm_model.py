"""
models/llm_model.py
MongoDB models for LLM integration.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional

from mongoengine import Document, EmbeddedDocument, fields
from models.base import BaseDocument


class LLMModelVersion(EmbeddedDocument):
    """LLM model version configuration."""
    
    version = fields.StringField(required=True)
    max_tokens = fields.IntField(default=4096)
    cost_per_1k_tokens = fields.FloatField(default=0.0)
    supports_streaming = fields.BooleanField(default=False)
    supports_json = fields.BooleanField(default=False)
    parameters = fields.DictField(default={})
    status = fields.StringField(default="active")
    created_at = fields.DateTimeField(default=datetime.utcnow)
    updated_at = fields.DateTimeField(default=datetime.utcnow)
    activated_at = fields.DateTimeField()
    activated_by = fields.StringField()
    deprecated_at = fields.DateTimeField()
    deprecated_by = fields.StringField()
    
    meta = {
        "collection": "llm_model_versions",
        "indexes": [
            {"fields": ["version", "status"]}
        ]
    }


class LLMModel(BaseDocument):
    """LLM model configuration."""
    
    provider = fields.StringField(required=True)
    model_id = fields.StringField(required=True)
    name = fields.StringField(required=True)
    description = fields.StringField(default="")
    max_tokens = fields.IntField(default=4096)
    cost_per_1k_tokens = fields.FloatField(default=0.0)
    supports_streaming = fields.BooleanField(default=False)
    supports_json = fields.BooleanField(default=False)
    parameters = fields.DictField(default={})
    tags = fields.ListField(fields.StringField(), default=[])
    organization_id = fields.ObjectIdField()
    current_version_id = fields.ObjectIdField()
    versions = fields.ListField(fields.EmbeddedDocumentField(LLMModelVersion), default=[])
    created_by = fields.StringField()
    updated_by = fields.StringField()
    created_at = fields.DateTimeField(default=datetime.utcnow)
    updated_at = fields.DateTimeField(default=datetime.utcnow)
    is_deleted = fields.BooleanField(default=False)
    
    meta = {
        "collection": "llm_models",
        "indexes": [
            {"fields": ["provider", "model_id"], "unique": True},
            {"fields": ["organization_id", "is_deleted"]},
            {"fields": ["tags"]},
            {"fields": ["created_at"]}
        ]
    }


class LLMOrganizationQuota(BaseDocument):
    """LLM usage quota for organizations."""
    
    organization_id = fields.ObjectIdField(required=True, unique=True)
    monthly_limit = fields.FloatField(required=True, default=100.0)
    warning_threshold = fields.FloatField(default=80.0)
    period_type = fields.StringField(default="monthly")
    current_usage = fields.FloatField(default=0.0)
    last_reset_at = fields.DateTimeField(default=datetime.utcnow)
    created_by = fields.StringField()
    updated_by = fields.StringField()
    created_at = fields.DateTimeField(default=datetime.utcnow)
    updated_at = fields.DateTimeField(default=datetime.utcnow)
    
    meta = {
        "collection": "llm_organization_quotas",
        "indexes": [
            {"fields": ["organization_id"], "unique": True},
            {"fields": ["created_at"]}
        ]
    }


class LLMUsage(BaseDocument):
    """LLM usage tracking record."""
    
    user_id = fields.ObjectIdField(required=True)
    organization_id = fields.ObjectIdField(required=True)
    provider = fields.StringField(required=True)
    model_id = fields.StringField(required=True)
    prompt_tokens = fields.IntField(required=True, default=0)
    completion_tokens = fields.IntField(required=True, default=0)
    total_tokens = fields.IntField(required=True)
    cost = fields.FloatField(required=True)
    request_id = fields.StringField(required=True, unique=True)
    session_id = fields.StringField()
    timestamp = fields.DateTimeField(default=datetime.utcnow)
    metadata = fields.DictField(default={})
    
    meta = {
        "collection": "llm_usage",
        "indexes": [
            {"fields": ["organization_id", "timestamp"]},
            {"fields": ["user_id", "timestamp"]},
            {"fields": ["provider", "model_id"]},
            {"fields": ["request_id"], "unique": True},
            {"fields": ["timestamp"]}
        ]
    }


class LLMPromptTemplate(BaseDocument):
    """LLM prompt template."""
    
    name = fields.StringField(required=True)
    template_text = fields.StringField(required=True)
    category = fields.StringField(required=True)
    description = fields.StringField(default="")
    variables = fields.ListField(fields.DictField(), default=[])
    provider = fields.StringField()
    model_id = fields.StringField()
    temperature = fields.FloatField(default=0.7)
    max_tokens = fields.IntField(default=1000)
    tags = fields.ListField(fields.StringField(), default=[])
    organization_id = fields.ObjectIdField()
    created_by = fields.StringField()
    updated_by = fields.StringField()
    deleted_by = fields.StringField()
    is_public = fields.BooleanField(default=False)
    usage_count = fields.IntField(default=0)
    last_used_at = fields.DateTimeField()
    created_at = fields.DateTimeField(default=datetime.utcnow)
    updated_at = fields.DateTimeField(default=datetime.utcnow)
    deleted_at = fields.DateTimeField()
    is_deleted = fields.BooleanField(default=False)
    
    meta = {
        "collection": "llm_prompt_templates",
        "indexes": [
            {"fields": ["organization_id", "name", "is_deleted"]},
            {"fields": ["category"]},
            {"fields": ["provider"]},
            {"fields": ["tags"]},
            {"fields": ["is_public", "created_at"]},
            {"fields": ["usage_count"]},
            {"fields": ["created_at"]}
        ]
    }


class LLMAnalysisNodeConfig(EmbeddedDocument):
    """Configuration for LLM analysis nodes."""
    
    provider = fields.StringField(required=True)
    model_id = fields.StringField(required=True)
    template_id = fields.StringField()
    prompt = fields.StringField(required=True)
    temperature = fields.FloatField(default=0.7)
    max_tokens = fields.IntField(default=1000)
    output_format = fields.StringField(default="text")
    variables = fields.DictField(default={})
    
    meta = {
        "collection": "llm_analysis_node_configs"
    }


class LLMChatSession(BaseDocument):
    """LLM chat session for form builder assistant."""
    
    user_id = fields.ObjectIdField(required=True)
    organization_id = fields.ObjectIdField(required=True)
    session_id = fields.StringField(required=True, unique=True)
    title = fields.StringField(default="New Chat")
    context_type = fields.StringField(default="form_builder")  # form_builder, analysis, dashboard
    context_id = fields.StringField()  # form_id, analysis_id, dashboard_id
    messages = fields.ListField(fields.DictField(), default=[])
    metadata = fields.DictField(default={})
    created_at = fields.DateTimeField(default=datetime.utcnow)
    updated_at = fields.DateTimeField(default=datetime.utcnow)
    last_message_at = fields.DateTimeField()
    
    meta = {
        "collection": "llm_chat_sessions",
        "indexes": [
            {"fields": ["user_id", "organization_id"]},
            {"fields": ["session_id"], "unique": True},
            {"fields": ["context_type", "context_id"]},
            {"fields": ["created_at"]},
            {"fields": ["last_message_at"]}
        ]
    }


class LLMChatMessage(BaseDocument):
    """Individual chat message in LLM sessions."""
    
    session_id = fields.StringField(required=True)
    role = fields.StringField(required=True)  # user, assistant, system
    content = fields.StringField(required=True)
    message_type = fields.StringField(default="text")  # text, code, form_suggestion, etc.
    metadata = fields.DictField(default={})
    timestamp = fields.DateTimeField(default=datetime.utcnow)
    
    meta = {
        "collection": "llm_chat_messages",
        "indexes": [
            {"fields": ["session_id", "timestamp"]},
            {"fields": ["role"]},
            {"fields": ["timestamp"]}
        ]
    }


class LLMABTest(BaseDocument):
    """A/B test configuration for LLM models."""
    
    test_id = fields.StringField(required=True, unique=True)
    name = fields.StringField(required=True)
    description = fields.StringField(default="")
    model_id = fields.ObjectIdField(required=True)
    versions = fields.ListField(fields.StringField(), required=True)
    traffic_split = fields.ListField(fields.IntField(), required=True)
    status = fields.StringField(default="active")  # active, paused, completed
    start_date = fields.DateTimeField(required=True)
    end_date = fields.DateTimeField(required=True)
    created_by = fields.StringField()
    created_at = fields.DateTimeField(default=datetime.utcnow)
    updated_at = fields.DateTimeField(default=datetime.utcnow)
    results = fields.DictField(default={})
    
    meta = {
        "collection": "llm_ab_tests",
        "indexes": [
            {"fields": ["test_id"], "unique": True},
            {"fields": ["model_id"]},
            {"fields": ["status"]},
            {"fields": ["start_date", "end_date"]},
            {"fields": ["created_at"]}
        ]
    }