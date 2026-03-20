from mongoengine import (
    StringField,
    ListField,
    DictField,
    BooleanField,
    EmbeddedDocument,
    EmbeddedDocumentField,
    DateTimeField,
    IntField,
    ValidationError,
)
from datetime import datetime, timezone
from models.base import BaseDocument, BaseEmbeddedDocument, SoftDeleteMixin


class WorkflowStep(BaseEmbeddedDocument):
    """
    A single step in an approval workflow.
    Supports serial (one approver) or parallel (multiple approvers) execution.
    """
    step_name = StringField(required=True)
    order = IntField(required=True)
    concurrency_type = StringField(choices=("serial", "parallel"), default="serial")
    approvers = ListField(StringField()) # List of User IDs
    approver_groups = ListField(StringField()) # List of Group IDs
    required_approvals = IntField(default=1) # Min approvals needed to pass this step
    
    # Escalation Logic
    timeout_hours = IntField(default=0) # 0 means no timeout
    escalation_action = StringField(choices=("auto_approve", "auto_reject", "notify_admin"), default="notify_admin")
    
    # Optional logic/actions
    actions = ListField(DictField()) # e.g. [{"type": "notify", "template": "..."}]

class ApprovalWorkflow(BaseDocument, SoftDeleteMixin):
    """
    Enterprise-grade multi-step approval workflow definition.
    """
    meta = {
        "collection": "approval_workflows",
        "indexes": ["trigger_form_id", "status", "organization_id"],
        "index_background": True,
    }
    name = StringField(required=True, trim=True)
    description = StringField()
    organization_id = StringField(required=True)
    trigger_form_id = StringField(required=True)
    status = StringField(choices=("active", "inactive"), default="active")
    
    steps = ListField(EmbeddedDocumentField("WorkflowStep"))
    
    created_by = StringField(required=True)
    is_template = BooleanField(default=False)
    
    def clean(self):
        if not self.steps:
            raise ValidationError("Workflow must have at least one step.")
        # Ensure step orders are unique/sequential
        orders = [s.order for s in self.steps]
        if len(orders) != len(set(orders)):
            raise ValidationError("Step orders must be unique.")
