from pydantic import Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from .base import SoftDeleteBaseSchema


class FormResponseSchema(SoftDeleteBaseSchema):
    project: Optional[str] = None
    form: str
    form_version: str
    organization_id: str

    data: Dict[str, Any]

    submitted_by: str
    submitted_at: Optional[datetime] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    status: Literal["submitted", "processed", "error", "archived"] = "submitted"
    review_status: Literal["pending", "approved", "rejected"] = "pending"

    meta_data: Optional[Dict[str, Any]] = None
    tags: List[str] = Field(default_factory=list)


class DynamicViewDefinitionSchema(SoftDeleteBaseSchema):
    organization_id: str
    view_name: str = Field(..., max_length=255)
    description: Optional[str] = None
    form: Optional[str] = None
    project: Optional[str] = None
    pipeline: List[Dict[str, Any]]

    tags: List[str] = Field(default_factory=list)
