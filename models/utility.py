"""
models/utility.py
Utility and background job models.
"""

from mongoengine import (
    StringField, ListField, EmbeddedDocumentField, ReferenceField, DictField,
    BooleanField, DateTimeField, IntField, EmbeddedDocument, FloatField
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument


class ExportJob(BaseDocument, SoftDeleteMixin):
    """Unified background job for exporting data (consolidated from BulkExport, AnalysisExport, and ExportJob)."""

    meta = {
        "collection": "export_jobs",
        "indexes": [
            {"fields": ["organization_id", "job_type"]},
            {"fields": ["organization_id", "status"]},
            {"fields": ["organization_id", "created_by"]},
            {"fields": ["created_at"], "expireAfterSeconds": 604800},  # 7 day TTL
            "organization_id",
            "status",
            "created_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    job_type = StringField(required=True)  # form_responses, analysis_results, bulk_exports, etc.
    name = StringField(required=True, trim=True)
    description = StringField()
    status = StringField(choices=["pending", "processing", "completed", "failed", "cancelled"], default="pending")
    format = StringField(choices=["csv", "excel", "pdf", "json"])
    
    # Form-specific fields (from BulkExport)
    form_ids = ListField(StringField())  # For bulk form exports
    
    # Analysis-specific fields (from AnalysisExport)
    analysis_id = ReferenceField("AnalysisBoard", reverse_delete_rule=2)  # For analysis exports
    node_ids = ListField(StringField())  # Which analysis nodes to export
    
    # Common export fields
    filters = DictField()
    columns = ListField(StringField())
    column_selection = ListField(StringField())  # From AnalysisExport
    sort_criteria = DictField()  # From AnalysisExport
    
    # File and progress tracking
    file_path = StringField()
    file_size = IntField()
    download_url = StringField()
    expires_at = DateTimeField()
    progress = FloatField(default=0.0)
    error_message = StringField()
    created_by = ReferenceField("User", reverse_delete_rule=3)
    created_at = DateTimeField()
    completed_at = DateTimeField()
    meta_data = DictField()


class ReportJobLog(BaseDocument):
    """Log entry for report generation jobs."""

    meta = {
        "collection": "report_job_logs",
        "indexes": [
            {"fields": ["organization_id", "job_id"]},
            {"fields": ["organization_id", "status"]},
            {"fields": ["created_at"], "expireAfterSeconds": 2592000},  # 30 day TTL
            "organization_id",
            "status",
            "created_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    job_id = StringField(required=True)
    job_type = StringField(required=True)
    status = StringField()
    start_time = DateTimeField()
    end_time = DateTimeField()
    duration_seconds = FloatField()
    records_processed = IntField()
    error_message = StringField()
    created_at = DateTimeField()
    meta_data = DictField()


class TranslationJob(BaseDocument, SoftDeleteMixin):
    """Background job for translating form content."""

    meta = {
        "collection": "translation_jobs",
        "indexes": [
            {"fields": ["organization_id", "form_id"]},
            {"fields": ["organization_id", "status"]},
            {"fields": ["organization_id", "target_language"]},
            {"fields": ["created_at"], "expireAfterSeconds": 604800},  # 7 day TTL
            "organization_id",
            "status",
            "created_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    form_id = ReferenceField("Form", required=True, reverse_delete_rule=2)
    target_language = StringField(required=True)
    source_language = StringField(default="en")
    status = StringField(choices=["pending", "processing", "completed", "failed"], default="pending")
    progress = FloatField(default=0.0)
    translated_fields = ListField(DictField())
    error_message = StringField()
    created_by = ReferenceField("User", reverse_delete_rule=3)
    completed_at = DateTimeField()
    meta_data = DictField()


class IdempotencyRecord(BaseDocument):
    """Idempotency key records to prevent duplicate operations."""

    meta = {
        "collection": "idempotency_records",
        "indexes": [
            {"fields": ["organization_id", "key"], "unique": True},
            {"fields": ["created_at"], "expireAfterSeconds": 86400},  # 24 hour TTL
            "organization_id",
            "created_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    key = StringField(required=True)
    operation = StringField(required=True)
    response_data = DictField()
    status_code = IntField()
    created_at = DateTimeField()
    expires_at = DateTimeField()


class DeadLetterTask(BaseDocument):
    """Dead letter queue for failed background tasks."""

    meta = {
        "collection": "dead_letter_tasks",
        "indexes": [
            {"fields": ["organization_id", "task_type"]},
            {"fields": ["organization_id", "status"]},
            {"fields": ["created_at"], "expireAfterSeconds": 2592000},  # 30 day TTL
            "organization_id",
            "status",
            "created_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    task_type = StringField(required=True)
    task_data = DictField()
    error_message = StringField()
    error_traceback = StringField()
    retry_count = IntField(default=0)
    max_retries = IntField(default=3)
    status = StringField(choices=["failed", "retry_scheduled", "archived"], default="failed")
    next_retry_at = DateTimeField()
    created_at = DateTimeField()
    meta_data = DictField()


class Tombstone(BaseDocument):
    """Tombstone records for deleted entities."""

    meta = {
        "collection": "tombstones",
        "indexes": [
            {"fields": ["organization_id", "entity_type", "entity_id"]},
            {"fields": ["organization_id", "deleted_at"]},
            {"fields": ["deleted_at"], "expireAfterSeconds": 2592000},  # 30 day TTL
            "organization_id",
            "entity_type",
            "deleted_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    entity_type = StringField(required=True)
    entity_id = StringField(required=True)
    deleted_by = ReferenceField("User", reverse_delete_rule=3)
    deleted_at = DateTimeField()
    reason = StringField()
    metadata = DictField()