from pydantic import Field
from typing import Optional, List, Dict, Any
from .base import BaseSchema
from .form import SectionSchema, ResponseTemplateSchema


class FormBlueprintSchema(BaseSchema):
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    sections: List[SectionSchema] = Field(default_factory=list)
    response_templates: List[ResponseTemplateSchema] = Field(default_factory=list)

    icon: Optional[str] = None
    estimated_completion_time: Optional[int] = None
    industry: Optional[str] = None
    usage_count: int = 0

    is_official: bool = False
    meta_data: Optional[Dict[str, Any]] = None


class ProjectBlueprintSchema(BaseSchema):
    name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    form_blueprints: List[str] = Field(default_factory=list)
    hierarchy_definition: Optional[Dict[str, Any]] = None

    is_template: bool = True
    meta_data: Optional[Dict[str, Any]] = None
