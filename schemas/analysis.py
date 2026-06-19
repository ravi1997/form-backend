"""
schemas/analysis.py
Pydantic schemas for analysis validation and serialization.
"""

from pydantic import BaseModel, Field, validator
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum


class ExecutionMode(str, Enum):
    ON_DEMAND = "on_demand"
    REACTIVE = "reactive"
    SCHEDULED = "scheduled"


class AnalysisTrigger(str, Enum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    REACTIVE = "reactive"
    ON_DEMAND = "on_demand"


class NodePortSchema(BaseModel):
    """Schema for node port definition."""
    
    id: str = Field(..., description="Port identifier")
    name: str = Field(..., description="Port display name")
    data_type: str = Field(..., description="Data type (table, value, dataframe, etc.)")
    description: Optional[str] = Field(None, description="Port description")
    is_required: bool = Field(True, description="Whether port is required")
    default_value: Optional[Dict[str, Any]] = Field(None, description="Default value")


class AnalysisNodeSchema(BaseModel):
    """Schema for analysis node."""
    
    id: str = Field(..., description="Node identifier")
    node_type: str = Field(..., description="Type of node")
    name: str = Field(..., description="Node display name")
    description: Optional[str] = Field(None, description="Node description")
    config: Dict[str, Any] = Field(default_factory=dict, description="Node configuration")
    input_ports: List[NodePortSchema] = Field(default_factory=list, description="Input ports")
    output_ports: List[NodePortSchema] = Field(default_factory=list, description="Output ports")
    position: Dict[str, float] = Field(default_factory=dict, description="UI position (x, y)")


class AnalysisEdgeSchema(BaseModel):
    """Schema for analysis edge."""
    
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    source_port: str = Field("output", description="Source port ID")
    target_port: str = Field("input", description="Target port ID")


class AnalysisGraphSchema(BaseModel):
    """Schema for analysis graph."""
    
    nodes: List[AnalysisNodeSchema] = Field(..., description="List of nodes")
    edges: List[AnalysisEdgeSchema] = Field(..., description="List of edges")
    
    @validator('nodes')
    def validate_nodes(cls, v):
        node_ids = [node.id for node in v]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Duplicate node IDs found")
        return v
    
    @validator('edges')
    def validate_edges(cls, v, values):
        if 'nodes' not in values:
            return v
        
        node_ids = {node.id for node in values['nodes']}
        for edge in v:
            if edge.source not in node_ids:
                raise ValueError(f"Edge source node '{edge.source}' not found")
            if edge.target not in node_ids:
                raise ValueError(f"Edge target node '{edge.target}' not found")
        return v


class AnalysisCreateSchema(BaseModel):
    """Schema for creating analysis."""
    
    project_id: str = Field(..., description="Project ID")
    name: str = Field(..., min_length=1, max_length=255, description="Analysis name")
    description: Optional[str] = Field(None, max_length=1000, description="Analysis description")
    linked_form_ids: Optional[List[str]] = Field(default_factory=list, description="Linked form IDs")
    execution_modes: List[ExecutionMode] = Field(default_factory=lambda: [ExecutionMode.ON_DEMAND])
    schedule: Optional[str] = Field(None, description="Cron schedule expression")
    reactive_debounce_ms: int = Field(1000, ge=0, description="Reactive debounce in milliseconds")
    graph: AnalysisGraphSchema = Field(..., description="Analysis graph")
    
    @validator('schedule')
    def validate_schedule(cls, v, values):
        if v is None:
            return v
        
        if 'execution_modes' in values and ExecutionMode.SCHEDULED not in values['execution_modes']:
            raise ValueError("Schedule can only be set when scheduled execution mode is enabled")
        
        # Basic cron validation (5 fields: minute hour day month weekday)
        if v and len(v.strip().split()) != 5:
            raise ValueError("Invalid cron expression format")
        
        return v


class AnalysisUpdateSchema(BaseModel):
    """Schema for updating analysis."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Analysis name")
    description: Optional[str] = Field(None, max_length=1000, description="Analysis description")
    linked_form_ids: Optional[List[str]] = Field(None, description="Linked form IDs")
    execution_modes: Optional[List[ExecutionMode]] = Field(None, description="Execution modes")
    schedule: Optional[str] = Field(None, description="Cron schedule expression")
    reactive_debounce_ms: Optional[int] = Field(None, ge=0, description="Reactive debounce in milliseconds")
    graph: Optional[AnalysisGraphSchema] = Field(None, description="Analysis graph")
    
    @validator('schedule')
    def validate_schedule(cls, v, values):
        if v is None:
            return v
        
        if 'execution_modes' in values and values['execution_modes'] is not None:
            if ExecutionMode.SCHEDULED not in values['execution_modes']:
                raise ValueError("Schedule can only be set when scheduled execution mode is enabled")
        
        # Basic cron validation
        if v and len(v.strip().split()) != 5:
            raise ValueError("Invalid cron expression format")
        
        return v


class AnalysisResponseSchema(BaseModel):
    """Schema for analysis response."""
    
    id: str
    project_id: str
    name: str
    description: Optional[str]
    linked_form_ids: List[str]
    execution_modes: List[ExecutionMode]
    schedule: Optional[str]
    reactive_debounce_ms: int
    graph: AnalysisGraphSchema
    status: str
    last_run_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class AnalysisRunResponseSchema(BaseModel):
    """Schema for analysis run response."""
    
    id: str
    analysis_id: str
    trigger: AnalysisTrigger
    triggered_by: Optional[str]
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    execution_time_seconds: Optional[float]
    node_statuses: Dict[str, Any]
    error_summary: Optional[str]
    created_at: datetime


class AnalysisResultSchema(BaseModel):
    """Schema for analysis result."""
    
    id: str
    analysis_id: str
    run_id: str
    node_id: str
    output_type: str
    data: Dict[str, Any]
    row_count: Optional[int]
    column_definitions: List[Dict[str, Any]]
    created_at: datetime


class AnalysisExportSchema(BaseModel):
    """Schema for analysis export."""
    
    id: str
    analysis_id: str
    run_id: Optional[str]
    format: str
    node_ids: List[str]
    file_path: Optional[str]
    file_size_bytes: Optional[int]
    status: str
    created_at: datetime
    expires_at: Optional[datetime]


class NodeExecutionSchema(BaseModel):
    """Schema for node execution status."""
    
    node_id: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error: Optional[str]


class AnalysisExecutionSchema(BaseModel):
    """Schema for analysis execution response."""
    
    run_id: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    execution_time_seconds: Optional[float]
    node_statuses: Dict[str, NodeExecutionSchema]
    results: Dict[str, AnalysisResultSchema]
    error_summary: Optional[str]