from mongoengine import (
    StringField,
    ListField,
    ReferenceField,
    EmbeddedDocumentField,
    DictField,
    IntField,
    BooleanField,
    DateTimeField,
)
from models.base import BaseDocument, BaseEmbeddedDocument, SoftDeleteMixin
from models.enumerations import (
    PERMISSION_CHOICES,
    ACCESS_LEVEL_CHOICES,
    APPROVAL_TYPE_CHOICES,
)


class UserGroup(BaseDocument, SoftDeleteMixin):
    """
    Groups users together for easier access management.
    Example: 'HR Department', 'Project Alpha Approvers'.
    """

    meta = {
        "collection": "user_groups",
        "indexes": ["name", "organization_id", "tags"],
        "index_background": True,
    }

    name = StringField(required=True, unique=True, trim=True)
    description = StringField()
    members = ListField(ReferenceField("User"))
    owners = ListField(ReferenceField("User"))
    organization_id = StringField()  # For multi-tenant support

    is_active = BooleanField(default=True)
    meta_data = DictField()
    tags = ListField(StringField())


class AccessEntry(BaseEmbeddedDocument):
    """
    Defines a single permission entry for a user or group.
    """

    grantee_type = StringField(choices=("user", "group"), required=True)
    grantee_user = ReferenceField("User")
    grantee_group = ReferenceField(UserGroup)
    permissions = ListField(StringField(choices=PERMISSION_CHOICES))


class ApprovalStep(BaseEmbeddedDocument):
    """
    A single step in an approval workflow.
    """

    step_name = StringField(required=True)
    order = IntField(default=1)

    # Who can approve at this step
    approvers = ListField(ReferenceField("User"))
    approver_groups = ListField(ReferenceField(UserGroup))

    # Step logic
    approval_type = StringField(choices=APPROVAL_TYPE_CHOICES, default="any_one")
    min_approvals_required = IntField(default=1)  # Used if type is 'parallel'

    # Custom scripts for this step
    on_approve_script = StringField()
    on_reject_script = StringField()


class ApprovalWorkflow(BaseDocument):
    """
    Defines the chain of approval for a form or project submission.
    Implements Maker-Checker logic through multi-step definitions.
    """

    meta = {
        "collection": "approval_workflows",
        "indexes": ["name", "tags"],
        "index_background": True,
    }

    name = StringField(required=True, unique=True)
    description = StringField()

    # Maker-Checker: Initiator group (Maker)
    initiator_groups = ListField(ReferenceField(UserGroup))

    # Workflow Steps (Checkers)
    steps = ListField(EmbeddedDocumentField(ApprovalStep))

    is_active = BooleanField(default=True)
    meta_data = DictField()
    tags = ListField(StringField())


class ResourceAccessControl(BaseDocument, SoftDeleteMixin):
    """
    The central ACL for any resource (Form or Project).
    """

    meta = {
        "collection": "resource_access_controls",
        "indexes": [
            # Compound index for fast lookup of a resource's security policy
            ("resource_type", "resource_id"),
            "tags",
        ],
        "index_background": True,
    }

    resource_type = StringField(choices=("form", "project"), required=True)
    resource_id = StringField(required=True)  # UUID of the Form or Project

    # High-level visibility
    access_level = StringField(choices=ACCESS_LEVEL_CHOICES, default="private")
    owner = ReferenceField("User", required=True)

    # Granular ACL
    access_list = ListField(EmbeddedDocumentField(AccessEntry))

    # Linked Approval Workflow
    approval_workflow = ReferenceField(ApprovalWorkflow)

    meta_data = DictField()
    tags = ListField(StringField())


class ExternalHook(BaseDocument, SoftDeleteMixin):
    """
    Registry for external hooks that require admin approval.
    """

    meta = {
        "collection": "external_hooks",
        "indexes": ["organization_id", "status", "url"],
        "index_background": True,
    }

    name = StringField(required=True)
    organization_id = StringField(required=True)
    url = StringField(required=True)
    method = StringField(default="POST")
    headers = DictField()
    
    # Validation schemas for input and output
    input_schema = DictField()
    output_schema = DictField()
    
    status = StringField(choices=("pending", "approved", "rejected"), default="pending")
    approved_by = ReferenceField("User")
    approved_at = DateTimeField()
    
    created_by = ReferenceField("User", required=True)
    is_active = BooleanField(default=True)
    
    meta_data = DictField()
