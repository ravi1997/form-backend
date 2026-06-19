"""
schemas/analysis_schemas.py
Analysis-related request/response schemas.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class AnalysisStatus(str, Enum):
    """Analysis status enumeration."""
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class AnalysisRunStatus(str, Enum):
    """Analysis run status enumeration."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TriggerType(str, Enum):
    """Analysis trigger type enumeration."""
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    FORM_SUBMISSION = "form_submission"
    WEBHOOK = "webhook"


class AnalysisNodeSchema(BaseModel):
    """Analysis node schema."""
    id: str = Field(..., description="Node ID")
    node_type: str = Field(..., description="Node type")
    name: str = Field(..., description="Node name")
    description: Optional[str] = Field(None, description="Node description")
    config: Dict[str, Any] = Field(default={}, description="Node configuration")
    position: Dict[str, float] = Field(default={"x": 0, "y": 0}, description="Node position")


class AnalysisEdgeSchema(BaseModel):
    """Analysis edge schema."""
    source_node_id: str = Field(..., description="Source node ID")
    source_port_id: str = Field(..., description="Source port ID")
    target_node_id: str = Field(..., description="Target node ID")
    target_port_id: str = Field(..., description="Target port ID")


class AnalysisCreateRequest(BaseModel):
    """Analysis creation request schema."""
    name: str = Field(..., min_length=1, max_length=200, description="Analysis name")
    description: Optional[str] = Field(None, max_length=1000, description="Analysis description")
    form_ids: List[str] = Field(default=[], description="Linked form IDs")
    nodes: List[AnalysisNodeSchema] = Field(..., min_items=1, description="Analysis nodes")
    edges: List[AnalysisEdgeSchema] = Field(default=[], description="Analysis edges")
    is_public: bool = Field(default=False, description="Is public analysis")


class AnalysisUpdateRequest(BaseModel):
    """Analysis update request schema."""
    name: Optional[str] = Field(None, min_length=1, max_length=200, description="Analysis name")
    description: Optional[str] = Field(None, max_length=1000, description="Analysis description")
    form_ids: Optional[List[str]] = Field(None, description="Linked form IDs")
    nodes: Optional[List[AnalysisNodeSchema]] = Field(None, min_items=1, description="Analysis nodes")
    edges: Optional[List[AnalysisEdgeSchema]] = Field(None, description="Analysis edges")
    status: Optional[AnalysisStatus] = Field(None, description="Analysis status")
    is_public: Optional[bool] = Field(None, description="Is public analysis")


class AnalysisResponse(BaseModel):
    """Analysis response schema."""
    id: str = Field(..., description="Analysis ID")
    name: str = Field(..., description="Analysis name")
    description: Optional[str] = Field(None, description="Analysis description")
    status: AnalysisStatus = Field(..., description="Analysis status")
    form_ids: List[str] = Field(..., description="Linked form IDs")
    node_count: int = Field(..., description="Number of nodes")
    edge_count: int = Field(..., description="Number of edges")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Update timestamp")


class AnalysisRunRequest(BaseModel):
    """Analysis run request schema."""
    analysis_id: str = Field(..., description="Analysis ID")
    trigger_type: TriggerType = Field(default=TriggerType.MANUAL, description="Trigger type")


class AnalysisRunResponse(BaseModel):
    """Analysis run response schema."""
    id: str = Field(..., description="Run ID")
    analysis_id: str = Field(..., description="Analysis ID")
    status: AnalysisRunStatus = Field(..., description="Run status")
    trigger_type: TriggerType = Field(..., description="Trigger type")
    started_at: Optional[datetime] = Field(None, description="Start time")
    completed_at: Optional[datetime] = Field(None, description="Completion time")
    execution_time_seconds: Optional[float] = Field(None, description="Execution time in seconds")
    error_message: Optional[str] = Field(None, description="Error message if failed")