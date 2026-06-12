from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class Widget(BaseModel):
    id: str = Field(..., description="Widget UUID")
    type: str = Field(..., description="Component type")
    position: Dict[str, float] = Field(..., description="x, y coordinates")
    size: Dict[str, float] = Field(..., description="width, height")
    z_index: int = Field(default=0)
    is_locked: bool = False
    properties: Dict[str, Any] = Field(default_factory=dict)
    data_binding: Optional[Dict[str, Any]] = None
    filters: List[Dict[str, Any]] = Field(default_factory=list)

class Canvas(BaseModel):
    width: float = Field(default=1200)
    height: float = Field(default=800)
    background_color: str = Field(default="#ffffff")
    widgets: List[Widget] = Field(default_factory=list)

class DashboardSettings(BaseModel):
    auto_refresh: bool = Field(default=False)
    refresh_interval_seconds: int = Field(default=300)
    theme: Dict[str, Any] = Field(default_factory=dict)

class Dashboard(BaseModel):
    org_id: str
    project_id: str
    name: str
    description: Optional[str] = None
    is_public: bool = Field(default=False)
    public_token: Optional[str] = None
    canvas: Canvas = Field(..., description="Canvas configuration")
    settings: DashboardSettings = Field(default_factory=DashboardSettings)
    linked_analysis_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    created_by: str
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    
    class Config:
        collection = "dashboards"
