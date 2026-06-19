"""
models/task.py
Task management and event processing models.
"""

from mongoengine import (
    StringField, ListField, EmbeddedDocumentField, ReferenceField, DictField,
    BooleanField, DateTimeField, IntField, EmbeddedDocument, FloatField
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument


class TaskStatus(str):
    """Task status constants."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class TaskPriority(str):
    """Task priority constants."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TaskDefinition(BaseEmbeddedDocument):
    """Task definition metadata."""

    task_type = StringField(required=True)
    name = StringField(required=True)
    description = StringField()
    handler_module = StringField(required=True)
    handler_function = StringField(required=True)
    default_timeout_seconds = IntField(default=300)
    max_retries = IntField(default=3)
    retry_delay_seconds = IntField(default=60)


class TaskExecution(BaseDocument, SoftDeleteMixin):
    """Task execution instance."""

    meta = {
        "collection": "task_executions",
        "indexes": [
            {"fields": ["organization_id", "task_type"]},
            {"fields": ["organization_id", "status"]},
            {"fields": ["organization_id", "created_by"]},
            {"fields": ["created_at"], "expireAfterSeconds": 604800},  # 7 day TTL
            "status",
            "scheduled_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True)
    task_id = StringField(required=True, unique=True)
    task_type = StringField(required=True)
    name = StringField(required=True)
    description = StringField()
    
    # Task definition
    handler_module = StringField(required=True)
    handler_function = StringField(required=True)
    
    # Scheduling and execution
    status = StringField(default=TaskStatus.PENDING)
    priority = StringField(default=TaskPriority.NORMAL)
    scheduled_at = DateTimeField()
    started_at = DateTimeField()
    completed_at = DateTimeField()
    timeout_seconds = IntField(default=300)
    
    # Retry configuration
    max_retries = IntField(default=3)
    retry_count = IntField(default=0)
    next_retry_at = DateTimeField()
    
    # Task data
    payload = DictField(default=dict)
    result_data = DictField(default=dict)
    error_message = StringField()
    error_traceback = StringField()
    
    # Execution metrics
    execution_time_seconds = FloatField()
    progress_percentage = FloatField(default=0.0)
    
    # Tracking
    created_by = ReferenceField("User", reverse_delete_rule=3)
    parent_task_id = StringField()
    child_task_ids = ListField(StringField(), default=list)
    
    created_at = DateTimeField()
    updated_at = DateTimeField()
    meta_data = DictField(default=dict)


class ScheduledTask(BaseDocument, SoftDeleteMixin):
    """Recurring scheduled task configuration."""

    meta = {
        "collection": "scheduled_tasks",
        "indexes": [
            {"fields": ["organization_id", "name"]},
            {"fields": ["organization_id", "task_type"]},
            {"fields": ["organization_id", "is_active"]},
            {"fields": ["next_run_at"]},
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True)
    name = StringField(required=True)
    description = StringField()
    task_type = StringField(required=True)
    
    # Schedule configuration
    cron_expression = StringField(required=True)
    timezone = StringField(default="UTC")
    next_run_at = DateTimeField()
    last_run_at = DateTimeField()
    
    # Task configuration
    payload = DictField(default=dict)
    timeout_seconds = IntField(default=300)
    max_retries = IntField(default=3)
    
    # Execution control
    is_active = BooleanField(default=True)
    run_immediately = BooleanField(default=False)
    
    # Tracking
    execution_count = IntField(default=0)
    failure_count = IntField(default=0)
    last_execution_status = StringField()
    average_execution_time_seconds = FloatField()
    
    created_by = ReferenceField("User", reverse_delete_rule=3)
    created_at = DateTimeField()
    updated_at = DateTimeField()
    meta_data = DictField(default=dict)


class TaskQueue(BaseDocument):
    """Task queue management and monitoring."""

    meta = {
        "collection": "task_queues",
        "indexes": [
            {"fields": ["queue_name"], "unique": True},
            {"fields": ["organization_id", "queue_name"]},
        ],
        "index_background": True,
    }

    queue_name = StringField(required=True, unique=True)
    organization_id = StringField()
    description = StringField()
    
    # Queue configuration
    max_concurrent_tasks = IntField(default=10)
    default_priority = StringField(default=TaskPriority.NORMAL)
    timeout_seconds = IntField(default=300)
    
    # Queue statistics
    pending_count = IntField(default=0)
    running_count = IntField(default=0)
    completed_count = IntField(default=0)
    failed_count = IntField(default=0)
    average_wait_time_seconds = FloatField(default=0.0)
    average_execution_time_seconds = FloatField(default=0.0)
    
    # Queue status
    is_active = BooleanField(default=True)
    last_activity_at = DateTimeField()
    
    created_at = DateTimeField()
    updated_at = DateTimeField()


class TaskDependency(BaseDocument):
    """Task dependency relationships."""

    meta = {
        "collection": "task_dependencies",
        "indexes": [
            {"fields": ["parent_task_id", "child_task_id"], "unique": True},
            {"fields": ["child_task_id"]},
            {"fields": ["organization_id"]},
        ],
        "index_background": True,
    }

    parent_task_id = StringField(required=True)
    child_task_id = StringField(required=True)
    organization_id = StringField(required=True)
    dependency_type = StringField(choices=["sequential", "parallel", "conditional"], default="sequential")
    
    # Dependency conditions
    condition_expression = StringField()
    condition_data = DictField(default=dict)
    
    created_at = DateTimeField()
    meta_data = DictField(default=dict)