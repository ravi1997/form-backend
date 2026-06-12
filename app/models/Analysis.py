from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class Node(BaseModel):
    id: str = Field(..., description="Node UUID")
    type: str = Field(..., description="Component type")
    position: Dict[str, float] = Field(..., description="x, y coordinates")
    size: Dict[str, float] = Field(..., description="width, height")
    properties: Dict[str, Any] = Field(default_factory=dict)
    label: Optional[str] = None
    is_disabled: bool = False

class Edge(BaseModel):
    id: str = Field(..., description="Edge UUID")
    from_node: str = Field(..., description="Source node ID")
    from_port: str = Field(..., description="Source port name")
    to_node: str = Field(..., description="Target node ID")
    to_port: str = Field(..., description="Target port name")
    label: Optional[str] = None

class Graph(BaseModel):
    nodes: List[Node] = Field(default_factory=list)
    edges: List[Edge] = Field(default_factory=list)

class Analysis(BaseModel):
    org_id: str
    project_id: str
    name: str
    description: Optional[str] = None
    linked_form_ids: List[str] = Field(default_factory=list)
    execution_modes: List[str] = Field(default=["on_demand"])
    schedule: Optional[str] = None
    reactive_debounce_ms: int = Field(default=1000)
    graph: Graph = Field(..., description="Node graph structure")
    last_run_id: Optional[str] = None
    status: str = Field(default="idle")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    created_by: str
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    
    class Config:
        collection = "analyses"
