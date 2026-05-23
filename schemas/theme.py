from typing import Any, Dict, List, Optional

from pydantic import Field

from schemas.base import InboundPayloadSchema, SoftDeleteBaseSchema


class ThemeSchema(SoftDeleteBaseSchema):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    organization_id: str
    created_by: str
    tokens: Dict[str, Any] = Field(default_factory=dict)
    branding: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    is_global: bool = False
    is_default: bool = False


class ThemeCreateSchema(ThemeSchema, InboundPayloadSchema):
    pass


class ThemeUpdateSchema(SoftDeleteBaseSchema, InboundPayloadSchema):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    organization_id: Optional[str] = None
    created_by: Optional[str] = None
    tokens: Optional[Dict[str, Any]] = None
    branding: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    is_global: Optional[bool] = None
    is_default: Optional[bool] = None
