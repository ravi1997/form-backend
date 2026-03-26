from pydantic import Field
from typing import Optional, List, Dict, Any, Literal
from .base import BaseSchema, BaseEmbeddedSchema


class UserGroupSchema(BaseSchema):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    members: List[str] = Field(default_factory=list)
    owners: List[str] = Field(default_factory=list)
    organization_id: Optional[str] = None

    is_active: bool = True
    meta_data: Optional[Dict[str, Any]] = None
    tags: List[str] = Field(default_factory=list)


class AccessEntrySchema(BaseEmbeddedSchema):
    grantee_type: Literal["user", "group"]
    grantee_user: Optional[str] = None
    grantee_group: Optional[str] = None
    permissions: List[
        Literal[
            "view",
            "edit",
            "delete",
            "publish",
            "export_data",
            "manage_access",
            "approve_submissions",
        ]
    ] = Field(default_factory=list)


class ApprovalStepSchema(BaseEmbeddedSchema):
    step_name: str = Field(..., max_length=255)
    order: int = 1

    approvers: List[str] = Field(default_factory=list)
    approver_groups: List[str] = Field(default_factory=list)

    approval_type: Literal["sequential", "parallel", "maker-checker", "any_one"] = (
        "any_one"
    )
    min_approvals_required: int = Field(default=1, ge=1)

    on_approve_script: Optional[str] = None
    on_reject_script: Optional[str] = None


class ApprovalWorkflowSchema(BaseSchema):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None

    initiator_groups: List[str] = Field(default_factory=list)
    steps: List[ApprovalStepSchema] = Field(default_factory=list)

    is_active: bool = True
    meta_data: Optional[Dict[str, Any]] = None
    tags: List[str] = Field(default_factory=list)


class ResourceAccessControlSchema(BaseSchema):
    resource_type: Literal["form", "project", "submission", "view"]
    resource_id: str

    access_level: Literal["private", "group", "organization", "public"] = "private"
    entries: List[AccessEntrySchema] = Field(default_factory=list)

    approval_workflow: Optional[str] = None

    is_active: bool = True
    meta_data: Optional[Dict[str, Any]] = None
    tags: List[str] = Field(default_factory=list)

class ExternalHookSchema(BaseSchema):
    name: str
    organization_id: str
    url: str
    method: str = "POST"
    headers: Optional[Dict[str, Any]] = Field(default_factory=dict)
    input_schema: Optional[Dict[str, Any]] = Field(default_factory=dict)
    output_schema: Optional[Dict[str, Any]] = Field(default_factory=dict)
    status: Literal["pending", "approved", "rejected"] = "pending"
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    created_by: str
    is_active: bool = True
    meta_data: Optional[Dict[str, Any]] = None
