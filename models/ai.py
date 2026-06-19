"""
models/ai.py
AI and LLM related models for intelligent form processing.
"""

from mongoengine import (
    StringField, ListField, EmbeddedDocumentField, ReferenceField, DictField,
    BooleanField, DateTimeField, IntField, EmbeddedDocument, FloatField
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument


class AIProvider(BaseDocument, SoftDeleteMixin):
    """AI service provider configuration."""

    meta = {
        "collection": "ai_providers",
        "indexes": [
            {"fields": ["provider_id"], "unique": True},
            {"fields": ["organization_id", "name"]},
            "is_active",
        ],
        "index_background": True,
    }

    provider_id = StringField(required=True, unique=True)
    name = StringField(required=True)
    description = StringField()
    provider_type = StringField(choices=["openai", "anthropic", "local", "custom"])
    
    # API configuration
    api_base_url = StringField()
    api_key = StringField()
    model_name = StringField()
    
    # Rate limiting and quota
    requests_per_minute = IntField(default=60)
    requests_per_hour = IntField(default=1000)
    max_tokens_per_request = IntField(default=4000)
    
    # Organization scoping
    organization_id = StringField()
    is_global = BooleanField(default=False)
    is_active = BooleanField(default=True)
    
    created_by = ReferenceField("User", reverse_delete_rule=3)
    created_at = DateTimeField()
    updated_at = DateTimeField()


class AIModelRegistry(BaseDocument, SoftDeleteMixin):
    """Registry of available AI models and their capabilities."""

    meta = {
        "collection": "ai_model_registry",
        "indexes": [
            {"fields": ["model_id"], "unique": True},
            {"fields": ["provider_id", "model_name"]},
            "capability",
            "is_active",
        ],
        "index_background": True,
    }

    model_id = StringField(required=True, unique=True)
    provider_id = StringField(required=True)
    model_name = StringField(required=True)
    display_name = StringField(required=True)
    description = StringField()
    
    # Model capabilities
    max_tokens = IntField()
    supports_streaming = BooleanField(default=False)
    supports_json_mode = BooleanField(default=False)
    supports_vision = BooleanField(default=False)
    supports_function_calling = BooleanField(default=False)
    
    # Performance characteristics
    input_cost_per_1k_tokens = FloatField(default=0.0)
    output_cost_per_1k_tokens = FloatField(default=0.0)
    avg_response_time_ms = FloatField()
    
    # Categorization
    capability = ListField(StringField(), default=list)  # text_generation, analysis, summarization, etc.
    model_size = StringField()  # small, medium, large
    
    is_active = BooleanField(default=True)
    created_at = DateTimeField()
    updated_at = DateTimeField()


class AIAnalysisTask(BaseDocument, SoftDeleteMixin):
    """AI-powered analysis tasks for forms and responses."""

    meta = {
        "collection": "ai_analysis_tasks",
        "indexes": [
            {"fields": ["organization_id", "task_type"]},
            {"fields": ["organization_id", "form_id"]},
            {"fields": ["organization_id", "status"]},
            "created_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True)
    task_type = StringField(required=True)  # sentiment_analysis, summarization, anomaly_detection, etc.
    name = StringField(required=True)
    description = StringField()
    
    # Task configuration
    form_id = ReferenceField("Form", reverse_delete_rule=2)
    response_ids = ListField(StringField(), default=list)
    analysis_config = DictField(default=dict)
    
    # AI model selection
    provider_id = StringField()
    model_id = StringField()
    
    # Task execution
    status = StringField(choices=["pending", "processing", "completed", "failed", "cancelled"], default="pending")
    progress = FloatField(default=0.0)
    result_data = DictField(default=dict)
    error_message = StringField()
    
    # Execution metrics
    tokens_used = IntField(default=0)
    execution_time_ms = FloatField()
    cost_usd = FloatField(default=0.0)
    
    created_by = ReferenceField("User", reverse_delete_rule=3)
    created_at = DateTimeField()
    started_at = DateTimeField()
    completed_at = DateTimeField()
    meta_data = DictField(default=dict)


class AIFormAssistant(BaseDocument, SoftDeleteMixin):
    """AI-powered form building assistant."""

    meta = {
        "collection": "ai_form_assistants",
        "indexes": [
            {"fields": ["organization_id", "name"]},
            {"fields": ["organization_id", "form_id"]},
            "is_active",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True)
    name = StringField(required=True)
    description = StringField()
    
    # Assistant configuration
    form_id = ReferenceField("Form", reverse_delete_rule=2)
    assistant_type = StringField(choices=["form_generator", "question_suggester", "validation_helper", "content_analyzer"])
    prompt_template = StringField()
    system_prompt = StringField()
    
    # AI model settings
    provider_id = StringField()
    model_id = StringField()
    temperature = FloatField(default=0.7)
    max_tokens = IntField(default=1000)
    
    # Usage tracking
    usage_count = IntField(default=0)
    last_used_at = DateTimeField()
    
    is_active = BooleanField(default=True)
    created_by = ReferenceField("User", reverse_delete_rule=3)
    created_at = DateTimeField()
    updated_at = DateTimeField()


class AITrainingData(BaseDocument, SoftDeleteMixin):
    """Training data for custom AI models."""

    meta = {
        "collection": "ai_training_data",
        "indexes": [
            {"fields": ["organization_id", "dataset_name"]},
            {"fields": ["organization_id", "data_type"]},
            {"fields": ["created_at"], "expireAfterSeconds": 2592000},  # 30 day TTL
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True)
    dataset_name = StringField(required=True)
    description = StringField()
    data_type = StringField(required=True)  # form_responses, user_feedback, etc.
    
    # Data storage
    file_path = StringField()
    record_count = IntField(default=0)
    file_size_bytes = IntField(default=0)
    
    # Training configuration
    target_model_id = StringField()
    training_config = DictField(default=dict)
    
    # Data quality
    validation_status = StringField(choices=["pending", "validated", "failed"], default="pending")
    quality_score = FloatField(min_value=0.0, max_value=1.0)
    
    created_by = ReferenceField("User", reverse_delete_rule=3)
    created_at = DateTimeField()
    expires_at = DateTimeField()
    meta_data = DictField(default=dict)