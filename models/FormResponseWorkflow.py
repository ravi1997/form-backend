import uuid
from datetime import datetime, timezone
from mongoengine import (
    Document,
    StringField,
    UUIDField,
    ListField,
    EmbeddedDocumentField,
    DateTimeField,
    DictField,
)
from models.base import BaseDocument, BaseEmbeddedDocument


class WorkflowApprovalStep(BaseEmbeddedDocument):
    """
    Individual step model defining target approvals and actors configuration.
    """

    id = UUIDField(required=True, default=uuid.uuid4)
    step_name = StringField(required=True)
    assigned_roles = ListField(
        StringField(), default=list
    )  # e.g., ["manager", "admin"]
    status = StringField(choices=["pending", "approved", "rejected"], default="pending")
    actioned_by = StringField()  # user_id of the actor who approved/rejected
    actioned_at = DateTimeField()
    comments = StringField()


class FormResponseWorkflow(BaseDocument):
    """
    Separate Workflow Engine collection keeping tracking of transition steps,
    assigned role queues, and transition histories completely isolated from core data.
    """

    meta = {
        "collection": "response_workflows",
        "indexes": ["response_id", "status"],
        "index_background": True,
    }

    id = UUIDField(primary_key=True, default=uuid.uuid4, binary=False)
    response_id = StringField(required=True)
    project_id = StringField(required=True)
    status = StringField(
        choices=["pending", "in_progress", "approved", "rejected"], default="pending"
    )
    steps = ListField(EmbeddedDocumentField(WorkflowApprovalStep), default=list)
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
