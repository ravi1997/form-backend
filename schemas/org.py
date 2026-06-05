"""
schemas/org.py
Pydantic schemas for Organization management.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from .base import SoftDeleteBaseSchema

class OrgCreateSchema(BaseModel):
    organization_id: str = Field(..., description="Unique alphanumeric identifier for the organization")
    name: str = Field(..., description="Legal/Corporate name of the organization")
    display_name: str = Field(..., description="Display name for branding")
    contact_email: Optional[str] = Field(None, description="Primary contact email")
    description: Optional[str] = Field(None, description="Brief description of the organization")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional custom metadata")

class OrgUpdateStatusSchema(BaseModel):
    status: str = Field(..., description="Target status ('active' or 'suspended')")

class OrgAssignAdminSchema(BaseModel):
    admin_user_id: str = Field(..., description="User ID of the designated organization administrator")

class OrgSchema(SoftDeleteBaseSchema):
    organization_id: str
    name: str
    display_name: str
    status: str
    admin_user_id: Optional[str] = None
    contact_email: Optional[str] = None
    description: Optional[str] = None
    metadata: Dict[str, Any] = {}
