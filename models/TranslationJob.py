from mongoengine import StringField, ListField, IntField, DictField, DateTimeField
from datetime import datetime, timezone
from models.base import BaseDocument


class TranslationJob(BaseDocument):
    meta = {
        "collection": "translation_jobs",
        "indexes": ["form_id", "status"],
        "index_background": True,
    }
    form_id = StringField(required=True)
    source_language = StringField(default="en")
    target_languages = ListField(StringField())
    status = StringField(
        default="pending"
    )  # 'pending', 'inProgress', 'completed', 'failed', 'cancelled'
    progress = IntField(default=0)
    total_fields = IntField(default=0)
    completed_fields = IntField(default=0)
    failed_fields = IntField(default=0)
    results = DictField()
    error_message = StringField()
    created_by = StringField()
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    started_at = DateTimeField()
    completed_at = DateTimeField()

    def to_dict(self):
        return {
            "id": str(self.id),
            "form_id": self.form_id,
            "status": self.status,
            "progress": self.progress,
            "source_language": self.source_language,
            "target_languages": self.target_languages,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "error_message": self.error_message,
        }
