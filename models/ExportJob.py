from datetime import datetime, timezone

from mongoengine import DateTimeField, IntField, StringField
from mongoengine import ListField

from models.base import BaseDocument


class ExportJob(BaseDocument):
    meta = {
        "collection": "export_jobs",
        "indexes": [
            ("analysis_run_id", "-created_at"),
            ("idempotency_key",),
            ("status", "-updated_at"),
        ],
        "index_background": True,
    }

    analysis_run_id = StringField(required=True)
    analysis_id = StringField()
    format = StringField(required=True)
    status = StringField(required=True, default="pending")
    node_ids = ListField(StringField(), default=list)
    file_path = StringField()
    file_size_bytes = IntField()
    retry_count = IntField(default=0)
    idempotency_key = StringField()
    last_error = StringField()
    expired_at = DateTimeField()

    def to_dict(self):
        data = super().to_dict()
        data["analysis_run_id"] = str(data.get("analysis_run_id") or "")
        data["run_id"] = data["analysis_run_id"]
        data["analysis_id"] = data.get("analysis_id")
        data["export_format"] = data.get("format")
        data["created_at"] = data.get("created_at")
        data["updated_at"] = data.get("updated_at")
        return data

    @property
    def run_id(self):
        return self.analysis_run_id

    @run_id.setter
    def run_id(self, value):
        self.analysis_run_id = value

    @property
    def expires_at(self):
        return self.expired_at

    @expires_at.setter
    def expires_at(self, value):
        self.expired_at = value
