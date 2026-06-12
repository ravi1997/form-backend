from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ConceptRegistry(BaseModel):
    concept_id: str = Field(..., description="Unique concept identifier")
    name: str = Field(..., description="Concept name")
    description: str = Field(..., description="Concept description")
    builder_type: str = Field(..., description="form_builder, analysis_coder, dashboard_builder")
    supported_component_types: List[str] = Field(default_factory=list)
    output_format: str
    version_support: bool = True
    collaboration_support: bool = True
    is_system: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    org_id: Optional[str] = None  # System level if None
    
    class Config:
        collection = "concept_registry"
