from datetime import datetime, timezone

from mongoengine import DateTimeField, DictField, IntField, ListField, StringField

from models.base import BaseDocument


class AnalysisRun(BaseDocument):
    meta = {
        "collection": "analysis_runs",
        "indexes": [("analysis_id", "-created_at")],
        "index_background": True,
    }

    analysis_id = StringField(required=True, db_field="analysis_id")
    trigger = StringField(required=True, default="on_demand")
    triggered_by = StringField()
    status = StringField(required=True, default="queued")
    started_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    completed_at = DateTimeField()
    celery_task_id = StringField()
    node_statuses = DictField(default=dict)
    error_summary = StringField()
    result_ids = DictField(default=dict)


class AnalysisResult(BaseDocument):
    meta = {
        "collection": "analysis_results",
        "indexes": [("run_id",), ("analysis_id", "node_id")],
        "index_background": True,
    }

    run_id = StringField(required=True, db_field="run_id")
    analysis_id = StringField(required=True, db_field="analysis_id")
    node_id = StringField(required=True)
    output_type = StringField(required=True, default="value")
    data = DictField()
    row_count = IntField()
    column_definitions = ListField(DictField(), default=list)
    cached_until = DateTimeField()


class AnalysisExport(BaseDocument):
    meta = {
        "collection": "analysis_exports",
        "indexes": [
            {"fields": ["expires_at"], "expireAfterSeconds": 0},
        ],
        "index_background": True,
    }

    analysis_id = StringField(required=True)
    run_id = StringField(required=True)
    format = StringField(required=True)
    node_ids = ListField(StringField(), default=list)
    file_path = StringField()
    file_size_bytes = IntField()
    status = StringField(required=True, default="queued")
    retry_count = IntField(default=0)
    last_error = StringField()
    idempotency_key = StringField()
    expires_at = DateTimeField()
    created_by = StringField()
