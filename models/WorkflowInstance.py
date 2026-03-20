from mongoengine import (
    StringField,
    ListField,
    ReferenceField,
    EmbeddedDocumentField,
    IntField,
    DateTimeField,
    DictField,
)
from datetime import datetime, timezone
from models.base import BaseDocument, BaseEmbeddedDocument, SoftDeleteMixin
from models.enumerations import WORKFLOW_STATUS_CHOICES


class ApprovalLog(BaseEmbeddedDocument):
    """
    Tracks individual actions within a workflow instance.
    """

    action_by = ReferenceField("User", required=True)
    action = StringField(
        choices=("approve", "reject", "revert", "claim"), required=True
    )
    comment = StringField(max_length=1000)
    timestamp = DateTimeField(default=lambda: datetime.now(timezone.utc))
    step_name = StringField()


class WorkflowInstance(BaseDocument, SoftDeleteMixin):
    """
    Tracks the live state of a submission through an approval workflow.
    This is where the actual 'Checking' happens after a 'Maker' submits.
    """

    meta = {
        "collection": "workflow_instances",
        "indexes": ["resource_id", "status", "current_step_order", "organization_id"],
        "index_background": True,
    }

    # Context
    organization_id = StringField(required=True)
    workflow_definition = ReferenceField("ApprovalWorkflow", required=True)
    resource_type = StringField(choices=("form_response",), default="form_response")
    resource_id = StringField(required=True)  # ID of the FormResponse

    # State
    status = StringField(choices=WORKFLOW_STATUS_CHOICES, default="pending")
    current_step_order = IntField(default=1)
    
    # Tracking for parallel steps
    # Maps step_order -> list of User IDs who approved
    step_approvals = DictField() 
    current_step_started_at = DateTimeField(default=lambda: datetime.now(timezone.utc))

    # Audit Trail
    history = ListField(EmbeddedDocumentField("ApprovalLog"))

    # Meta
    started_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    completed_at = DateTimeField()
    meta_data = DictField()
