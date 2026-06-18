"""
models/analysis.py
Analysis and data processing models.
"""

from mongoengine import (
    StringField, ListField, EmbeddedDocumentField, ReferenceField, DictField,
    BooleanField, DateTimeField, IntField, EmbeddedDocument, FloatField
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument


class AnalysisNode(BaseEmbeddedDocument):
    """Individual node in an analysis pipeline."""

    id = StringField(required=True)
    node_type = StringField(required=True)
    name = StringField(required=True)
    description = StringField()
    config = DictField()
    input_ports = ListField(DictField())
    output_ports = ListField(DictField())
    position = DictField()  # x, y coordinates for UI
    meta_data = DictField()


class AnalysisEdge(BaseEmbeddedDocument):
    """Connection between analysis nodes."""

    source_node_id = StringField(required=True)
    source_port_id = StringField(required=True)
    target_node_id = StringField(required=True)
    target_port_id = StringField(required=True)
    meta_data = DictField()


class AnalysisBoard(BaseDocument, SoftDeleteMixin):
    """Analysis pipeline configuration."""

    meta = {
        "collection": "analysis_boards",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            "organization_id",
            "created_by",
            "status",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    description = StringField()
    form_ids = ListField(ReferenceField("Form", reverse_delete_rule=3))
    nodes = ListField(EmbeddedDocumentField(AnalysisNode))
    edges = ListField(EmbeddedDocumentField(AnalysisEdge))
    created_by = ReferenceField("User", reverse_delete_rule=3)
    status = StringField(choices=("draft", "active", "archived"), default="draft")
    is_public = BooleanField(default=False)
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
    analysis_id = ReferenceField("AnalysisBoard", required=True, reverse_delete_rule=2)
    run_id = StringField(required=True)
    status = StringField(choices=("queued", "running", "completed", "failed", "cancelled"), default="queued")
    trigger_type = StringField(choices=("manual", "scheduled", "form_submission", "webhook"))
    triggered_by = ReferenceField("User", reverse_delete_rule=3)
    started_at = DateTimeField()
    completed_at = DateTimeField()
    execution_time_seconds = FloatField()
    node_statuses = DictField()  # node_id -> status
    error_message = StringField()
    result_ids = DictField()  # node_id -> result_id
    meta_data = DictField()


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
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    analysis_id = ReferenceField("AnalysisBoard", required=True, reverse_delete_rule=2)
    run_id = StringField(required=True)
    node_id = StringField(required=True)
    result_type = StringField(choices=("table", "chart", "value", "file", "error"))
    data = DictField()
    row_count = IntField()
    column_definitions = ListField(DictField())
    file_path = StringField()
    file_size = IntField()
    error_details = DictField()
    cached_until = DateTimeField()
    meta_data = DictField()


class AnalysisExport(BaseDocument, SoftDeleteMixin):
    """Export configuration and results for analysis data."""

    meta = {
        "collection": "analysis_exports",
        "indexes": [
            {"fields": ["organization_id", "analysis_id"]},
            "organization_id",
            "analysis_id",
            "status",
            "created_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    analysis_id = ReferenceField("AnalysisBoard", required=True, reverse_delete_rule=2)
    name = StringField(required=True, trim=True)
    description = StringField()
    export_format = StringField(choices=("csv", "excel", "pdf", "json"))
    node_ids = ListField(StringField())  # Which nodes to export
    column_selection = ListField(StringField())
    filter_criteria = DictField()
    sort_criteria = DictField()
    status = StringField(choices=("pending", "generating", "ready", "failed", "expired"), default="pending")
    file_path = StringField()
    file_size = IntField()
    download_url = StringField()
    expires_at = DateTimeField()
    created_by = ReferenceField("User", reverse_delete_rule=3)
    meta_data = DictField()