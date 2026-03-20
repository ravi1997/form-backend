from pydantic import Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from .base import SoftDeleteBaseSchema, BaseEmbeddedSchema


class ApprovalLogSchema(BaseEmbeddedSchema):
    action_by: str
    action: Literal["approve", "reject", "revert", "claim"]
    comment: Optional[str] = Field(None, max_length=1000)
    timestamp: Optional[datetime] = None
    step_name: Optional[str] = None


class WorkflowInstanceSchema(SoftDeleteBaseSchema):
    organization_id: str
    workflow_definition: str
    resource_type: Literal["form_response"] = "form_response"
    resource_id: str

    status: Literal["pending", "in_review", "approved", "rejected", "reverted"] = (
        "pending"
    )
    current_step_order: int = 1

    history: List[ApprovalLogSchema] = Field(default_factory=list)

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    meta_data: Optional[Dict[str, Any]] = None
