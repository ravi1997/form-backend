import uuid
from datetime import datetime, timezone
from mongoengine import DateTimeField, DictField, StringField, ListField
from .base import BaseDocument


class DeadLetterTask(BaseDocument):
    meta = {
        "collection": "dead_letter_tasks",
        "indexes": [
            "task_id",
            "task_name",
            "-created_at",
            "organization_id",
        ],
        "index_background": True,
    }

    task_id = StringField(required=True, unique=True)
    task_name = StringField(required=True)
    args = ListField()
    kwargs = DictField()
    exception = StringField()
    traceback = StringField()
