from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class PropertyDef(BaseModel):
    key: str = Field(..., description="Property key")
    label: str = Field(..., description="Property label")
    type: str = Field(..., description="Property type")
    default: Any = None
    required: bool = False
    options: List[Any] = Field(default_factory=list)
    group: str = Field(default="General")

class PortDef(BaseModel):
    id: str = Field(..., description="Port identifier")
    label: str = Field(..., description="Port label")
    data_type: str = Field(..., description="Data type")

class ComponentSchema(BaseModel):
    plugin_id: str = Field(..., description="Plugin identifier")
    plugin_version: str = Field(..., description="Plugin version")
    concept_id: str = Field(..., description="Concept identifier")
    component_type: str = Field(..., description="Component type")
    display_name: str = Field(..., description="Display name")
    description: str = Field(..., description="Component description")
    icon_path: Optional[str] = None
    composition: List[Dict[str, Any]] = Field(default_factory=list)
    properties: List[PropertyDef] = Field(default_factory=list)
    input_ports: List[PortDef] = Field(default_factory=list)
    output_ports: List[PortDef] = Field(default_factory=list)
    widget_config: Dict[str, Any] = Field(default_factory=dict)
    preview_schema: Dict[str, Any] = Field(default_factory=dict)
    offline_support: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        collection = "component_schemas"
