"""
models/workflow.py
Workflow and approval process models.
"""

from mongoengine import (
    StringField, ListField, EmbeddedDocumentField, ReferenceField, DictField,
    BooleanField, DateTimeField, IntField, EmbeddedDocument, ValidationError
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument

# Import choice constants
from models.base import (
    APPROVAL_TYPE_CHOICES, WORKFLOW_STATUS_CHOICES, ROLE_CHOICES
)


class WorkflowStep(BaseEmbeddedDocument):
    """Individual step in a workflow."""

    id = StringField(required=True)
    name = StringField(required=True)
    description = StringField()
    step_type = StringField(choices=("approval", "notification", "action", "condition"))
    approval_type = StringField(choices=APPROVAL_TYPE_CHOICES)
    approver_groups = ListField(StringField())
    assignees = ListField(ReferenceField("User"))
    roles = ListField(StringField(choices=ROLE_CHOICES))
    required_approvals = IntField(default=1)
    conditions = ListField(DictField())
    actions = ListField(DictField())
    order = IntField(default=0)
    is_required = BooleanField(default=True)
    timeout_minutes = IntField()
    meta_data = DictField()


class WorkflowTransition(BaseEmbeddedDocument):
    """Transition between workflow steps."""

    from_step_id = StringField(required=True)
    to_step_id = StringField(required=True)
    condition = DictField()
    is_default = BooleanField(default=False)
    meta_data = DictField()





class Workflow(BaseDocument, SoftDeleteMixin):
    """Workflow definition."""

    meta = {
        "collection": "workflows",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            {"fields": ["organization_id", "slug"], "unique": True, "sparse": True},
            "organization_id",
            "entity_type",
            "status",
            "created_by",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    slug = StringField(trim=True)
    description = StringField()
    entity_type = StringField(required=True)  # form_response, analysis_run, etc.
    trigger_conditions = ListField(DictField())
    steps = ListField(EmbeddedDocumentField(WorkflowStep))
    transitions = ListField(EmbeddedDocumentField(WorkflowTransition))
    created_by = ReferenceField("User", reverse_delete_rule=3)
    status = StringField(choices=("draft", "active", "archived"), default="draft")
    is_default = BooleanField(default=False)
    version = StringField(default="1.0")
    meta_data = DictField()

    def clean(self):
        # Validate step IDs are unique
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValidationError("Step IDs must be unique within a workflow.")
        
        # Validate transitions reference valid steps
        step_id_set = set(step_ids)
        for transition in self.transitions:
            if transition.from_step_id not in step_id_set:
                raise ValidationError(f"Transition from_step_id '{transition.from_step_id}' references invalid step.")
            if transition.to_step_id not in step_id_set:
                raise ValidationError(f"Transition to_step_id '{transition.to_step_id}' references invalid step.")


class ApprovalLog(BaseEmbeddedDocument):
    """Log entry for workflow approval actions."""

    action_by = StringField()
    action = StringField(choices=("approve", "reject", "revert", "claim"))
    comment = StringField()
    timestamp = DateTimeField()
    step_name = StringField()


class WorkflowInstance(BaseDocument, SoftDeleteMixin):
    """Active instance of a workflow."""

    meta = {
        "collection": "workflow_instances",
        "indexes": [
            {"fields": ["organization_id", "workflow_id"]},
            {"fields": ["organization_id", "entity_type", "entity_id"]},
            "organization_id",
            "workflow_id",
            "status",
            "current_step_id",
            "created_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    workflow_id = ReferenceField("Workflow", required=True, reverse_delete_rule=2)
    workflow_definition = ReferenceField("Workflow", reverse_delete_rule=2)
    entity_type = StringField(required=True)
    entity_id = StringField(required=True)
    current_step_id = StringField()
    current_step_order = IntField(default=0)
    status = StringField(choices=WORKFLOW_STATUS_CHOICES, default="pending")
    started_by = ReferenceField("User", reverse_delete_rule=3)
    started_at = DateTimeField()
    completed_at = DateTimeField()
    step_history = ListField(DictField())
    history = ListField(EmbeddedDocumentField(ApprovalLog))
    step_approvals = DictField()
    current_assignees = ListField(ReferenceField("User", reverse_delete_rule=3))
    current_step_started_at = DateTimeField()
    data = DictField()
    meta_data = DictField()


class WorkflowTemplate(BaseDocument, SoftDeleteMixin):
    """Reusable workflow templates."""

    meta = {
        "collection": "workflow_templates",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            "organization_id",
            "category",
            "is_public",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    description = StringField()
    category = StringField()
    entity_type = StringField(required=True)
    workflow_definition = DictField()  # Complete workflow structure
    parameters = DictField()  # Configurable parameters
    created_by = ReferenceField("User", reverse_delete_rule=3)
    is_public = BooleanField(default=False)
    is_system = BooleanField(default=False)
    usage_count = IntField(default=0)
    meta_data = DictField()


class ApprovalRequest(BaseDocument, SoftDeleteMixin):
    """Individual approval request."""

    meta = {
        "collection": "approval_requests",
        "indexes": [
            {"fields": ["organization_id", "workflow_instance_id"]},
            {"fields": ["organization_id", "approver_id"]},
            {"fields": ["organization_id", "entity_type", "entity_id"]},
            "organization_id",
            "status",
            "created_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    workflow_instance_id = ReferenceField("WorkflowInstance", required=True, reverse_delete_rule=2)
    step_id = StringField(required=True)
    approver_id = ReferenceField("User", required=True, reverse_delete_rule=2)
    entity_type = StringField(required=True)
    entity_id = StringField(required=True)
    status = StringField(choices=("pending", "approved", "rejected", "expired"), default="pending")
    decision = StringField(choices=("approve", "reject"))
    comments = StringField()
    decided_at = DateTimeField()
    expires_at = DateTimeField()
    created_at = DateTimeField()
    meta_data = DictField()