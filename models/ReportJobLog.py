import uuid
from datetime import datetime, timezone
from mongoengine import (
    Document,
    StringField,
    UUIDField,
    IntField,
    DateTimeField,
)
from models.base import BaseDocument

class ReportJobLog(BaseDocument):
    """
    Standalone auditing log capturing every automated custom PDF/HTML report compilation.
    Keeps parent Project document from bloating while guaranteeing robust observability.
    """
    meta = {
        "collection": "report_job_logs",
        "indexes": ["project_id", "config_id", "status"],
        "index_background": True,
    }

    id = UUIDField(primary_key=True, default=uuid.uuid4, binary=False)
    project_id = StringField(required=True)
    config_id = StringField(required=True)
    status = StringField(required=True, choices=["pending", "compiling", "success", "failed"], default="pending")
    trigger_reason = StringField(required=True)  # "Cron Schedule" or "Threshold Hit"
    executed_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    duration_ms = IntField(default=0)
    file_url = StringField()
    error_message = StringField()
