"""
models/analysis.py
Analysis and data processing models for the Form Builder Platform.
"""

from mongoengine import (
    StringField, ListField, EmbeddedDocumentField, ReferenceField, DictField,
    BooleanField, DateTimeField, IntField, EmbeddedDocument, FloatField,
    ObjectIdField, URLField
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument
from datetime import datetime, timezone


class NodePort(BaseEmbeddedDocument):
    """Port definition for analysis nodes."""

    id = StringField(required=True)
    name = StringField(required=True)
    data_type = StringField(required=True, choices=[
        "table", "value", "dataframe", "string", "number", "boolean", "array", "object"
    ])
    description = StringField()
    is_required = BooleanField(default=True)
    default_value = DictField()


class AnalysisNode(BaseEmbeddedDocument):
    """Individual node in an analysis pipeline."""

    id = StringField(required=True)
    node_type = StringField(required=True)
    name = StringField(required=True)
    description = StringField()
    config = DictField()
    input_ports = ListField(EmbeddedDocumentField(NodePort))
    output_ports = ListField(EmbeddedDocumentField(NodePort))
    position = DictField()  # x, y coordinates for UI
    meta_data = DictField()


class AnalysisEdge(BaseEmbeddedDocument):
    """Connection between analysis nodes."""

    source = StringField(required=True)  # source node id
    target = StringField(required=True)  # target node id
    source_port = StringField(default="output")  # source port id
    target_port = StringField(default="input")  # target port id
    meta_data = DictField()


class Analysis(BaseDocument, SoftDeleteMixin):
    """Analysis pipeline configuration."""

    meta = {
        "collection": "analyses",
        "indexes": [
            {"fields": ["organization_id", "project_id", "name"]},
            "organization_id",
            "project_id",
            "created_by",
            "status",
            "last_run_id",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    project_id = ReferenceField("Project", required=True, reverse_delete_rule=3)
    name = StringField(required=True, trim=True)
    description = StringField()
    linked_form_ids = ListField(ReferenceField("Form", reverse_delete_rule=3))
    execution_modes = ListField(StringField(choices=["on_demand", "reactive", "scheduled"]))
    schedule = StringField()  # cron expression
    reactive_debounce_ms = IntField(default=1000)
    graph = DictField(required=True)  # {nodes: [], edges: []}
    last_run_id = ReferenceField("AnalysisRun")
    status = StringField(choices=["idle", "running", "error"], default="idle")
    created_by = ReferenceField("User", reverse_delete_rule=3)
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    meta_data = DictField()


class AnalysisRun(BaseDocument, SoftDeleteMixin):
    """Execution instance of an analysis."""

    meta = {
        "collection": "analysis_runs",
        "indexes": [
            {"fields": ["organization_id", "analysis_id"]},
            "organization_id",
            "analysis_id",
            "status",
            "started_at",
            "completed_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    analysis_id = ReferenceField(Analysis, required=True, reverse_delete_rule=2)
    trigger = StringField(required=True, choices=["on_demand", "scheduled", "reactive", "manual"])
    triggered_by = ReferenceField("User", reverse_delete_rule=3)
    status = StringField(required=True, choices=["queued", "running", "completed", "failed", "partial"])
    started_at = DateTimeField()
    completed_at = DateTimeField()
    celery_task_id = StringField()
    node_statuses = DictField()  # node_id -> {status, started_at, completed_at, error}
    error_summary = StringField()
    result_ids = DictField()  # node_id -> result_id
    execution_time_seconds = FloatField()
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))


class AnalysisResult(BaseDocument, SoftDeleteMixin):
    """Result of an analysis node execution."""

    meta = {
        "collection": "analysis_results",
        "indexes": [
            {"fields": ["organization_id", "analysis_id", "run_id"]},
            {"fields": ["organization_id", "node_id"]},
            "organization_id",
            "analysis_id",
            "run_id",
            "node_id",
            "created_at",
            "cached_until",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    analysis_id = ReferenceField(Analysis, required=True, reverse_delete_rule=2)
    run_id = StringField(required=True)
    node_id = StringField(required=True)
    output_type = StringField(required=True, choices=["table", "value", "dataframe", "chart_data", "error"])
    data = DictField()
    row_count = IntField()
    column_definitions = ListField(DictField())
    cached_until = DateTimeField()
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))


class AnalysisExport(BaseDocument, SoftDeleteMixin):
    """Export job for analysis results."""

    meta = {
        "collection": "analysis_exports",
        "indexes": [
            {"fields": ["organization_id", "analysis_id"]},
            "organization_id",
            "analysis_id",
            "run_id",
            "status",
            "created_at",
            "expires_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    analysis_id = ReferenceField(Analysis, required=True, reverse_delete_rule=2)
    run_id = StringField()
    format = StringField(required=True, choices=["csv", "excel", "pdf"])
    node_ids = ListField(StringField())
    file_path = StringField()
    file_size_bytes = IntField()
    status = StringField(required=True, choices=["queued", "generating", "ready", "failed", "expired"])
    expires_at = DateTimeField()  # TTL 7 days
    created_by = ReferenceField("User", reverse_delete_rule=3)
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))


# Keep AnalysisBoard for backward compatibility but mark as deprecated
class AnalysisBoard(BaseDocument, SoftDeleteMixin):
    """DEPRECATED: Use Analysis instead. Kept for backward compatibility."""

    meta = {
        "collection": "analysis_boards",
        "indexes": [
            {"fields": ["organization_id", "name"]},
            "organization_id",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    description = StringField()
    form_ids = ListField(ReferenceField("Form", reverse_delete_rule=3))
    created_by = ReferenceField("User", reverse_delete_rule=3)
    status = StringField(choices=("draft", "active", "archived"), default="draft")
    is_public = BooleanField(default=False)
    meta_data = DictField()
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = DateTimeField(default=lambda: datetime.now(timezone.utc))