import uuid
from mongoengine import (
    UUIDField,
    StringField,
    ListField,
    DictField,
)
from models.base import BaseDocument, SoftDeleteMixin


class FormCommit(BaseDocument, SoftDeleteMixin):
    """
    Represents a single commit snapshot delta in the form's version control DAG.
    Inherits from BaseDocument for automatic UUID, timestamps, and tenant isolation on organization_id.
    """

    meta = {
        "collection": "form_commits",
        "indexes": [
            {"fields": ["form_id"]},
            {"fields": ["parent_commit_id"]},
            {"fields": ["organization_id", "form_id"]},
        ],
    }

    form_id = UUIDField(required=True, binary=False)
    parent_commit_id = UUIDField(binary=False)
    author_id = StringField(required=True)
    message = StringField(default="")
    patch = ListField(DictField(), default=list)

    def to_dict(self):
        """Standardizes dict conversion with clean UUID representations."""
        data = super().to_dict()
        if "form_id" in data and data["form_id"]:
            data["form_id"] = str(data["form_id"])
        if "parent_commit_id" in data and data["parent_commit_id"]:
            data["parent_commit_id"] = str(data["parent_commit_id"])
        return data
