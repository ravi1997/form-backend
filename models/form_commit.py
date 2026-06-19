"""
models/form_commit.py
Form commit model for Git-like versioning system.
"""

from mongoengine import (
    StringField, ListField, ReferenceField, DictField,
    DateTimeField, EmbeddedDocument, ObjectIdField
)
from models.base import BaseDocument
from models.identity import User


class FormCommit(BaseDocument):
    """Individual commit in the form version history."""
    
    meta = {
        "collection": "form_commits",
        "indexes": [
            {"fields": ["form_id", "commit_id"], "unique": True},
            "form_id",
            "organization_id",
            "branch",
            "timestamp",
            ("form_id", "branch"),
        ],
        "index_background": True,
    }
    
    form_id = ObjectIdField(required=True)
    commit_id = StringField(required=True, max_length=64)  # SHA-256 hash (first 64 chars)
    organization_id = StringField(required=True)
    author_id = ObjectIdField(required=True)
    message = StringField(required=True, max_length=1000)
    branch = StringField(required=True, default="main")
    parent_ids = ListField(StringField(), default=list)
    timestamp = DateTimeField(required=True)
    schema = DictField(required=True)  # Complete form schema at this commit
    
    def __str__(self):
        return f"{self.commit_id[:8]} - {self.message}"


class PendingMerge(BaseDocument):
    """Tracks merge conflicts that need resolution."""
    
    meta = {
        "collection": "pending_merges",
        "indexes": [
            "form_id",
            "organization_id",
            "status",
            ("form_id", "branch_name"),
        ],
        "index_background": True,
    }
    
    form_id = ObjectIdField(required=True)
    organization_id = StringField(required=True)
    branch_name = StringField(required=True)
    base_commit_id = StringField(required=True)
    their_commit_id = StringField(required=True)
    our_changes = DictField(required=True)
    conflict_fields = ListField(StringField(), default=list)
    status = StringField(choices=["pending", "resolved", "abandoned"], default="pending")
    resolver_id = ObjectIdField()
    resolved_at = DateTimeField()
    created_at = DateTimeField()
    created_by = ObjectIdField(required=True)
    
    def __str__(self):
        return f"Merge {self.branch_name} -> main ({self.status})"


class EditSession(BaseDocument):
    """Tracks active editing sessions for presence awareness."""
    
    meta = {
        "collection": "edit_sessions",
        "indexes": [
            ("entity_type", "entity_id"),
            "user_id",
            "organization_id",
            "last_ping_at",
        ],
        "index_background": True,
    }
    
    entity_type = StringField(required=True, choices=["form", "section", "question"])
    entity_id = ObjectIdField(required=True)
    user_id = ObjectIdField(required=True)
    organization_id = StringField(required=True)
    started_at = DateTimeField(required=True)
    last_ping_at = DateTimeField(required=True)
    
    def __str__(self):
        return f"{self.user_id} editing {self.entity_type}:{self.entity_id}"