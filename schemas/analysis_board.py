from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from schemas.base import (
    BaseSchema,
    BaseEmbeddedSchema,
    SoftDeleteBaseSchema,
    InboundPayloadSchema,
)


class AnalysisNodeSchema(BaseEmbeddedSchema):
    """
    Validation schema for an embedded calculation node.
    """
    title: str
    node_type: str = "aggregation"  # "aggregation", "aspect_calculation", "filter"
    function_id: str  # SUM, COUNT, AVERAGE, STD_DEV, CORRELATION, etc.
    target_form_id: str
    target_field_id: str
    secondary_field_id: Optional[str] = None
    filters: Dict[str, Any] = Field(default_factory=dict)
    position_x: float = 0.0
    position_y: float = 0.0
    inputs: List[str] = Field(default_factory=list)
    config: Dict[str, Any] = Field(default_factory=dict)


class AnalysisBoardSchema(SoftDeleteBaseSchema):
    """
    Canonical output representation schema for Analysis Boards.
    """
    title: str
    project_id: str
    organization_id: str
    description: Optional[str] = None
    nodes: List[AnalysisNodeSchema] = Field(default_factory=list)
    created_by: str


class AnalysisBoardCreateSchema(BaseModel, InboundPayloadSchema):
    """
    Strict validation schema for incoming creation requests.
    """
    title: str
    project_id: str
    description: Optional[str] = None
    nodes: List[AnalysisNodeSchema] = Field(default_factory=list)


class AnalysisBoardUpdateSchema(BaseModel, InboundPayloadSchema):
    """
    Strict validation schema for update requests.
    """
    title: Optional[str] = None
    description: Optional[str] = None
    nodes: Optional[List[AnalysisNodeSchema]] = None
