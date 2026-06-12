from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class Plugin(BaseModel):
    plugin_id: str = Field(..., description="Unique plugin slug")
    name: str = Field(..., description="Plugin display name")
    description: str = Field(..., description="Plugin description")
    author: Dict[str, str] = Field(default_factory=dict)
    version: str = Field(..., description="Semantic version")
    manifest: Dict[str, Any] = Field(..., description="Full manifest JSON")
    status: str = Field(default="active")
    concept_targets: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)
    installed_at: Optional[datetime] = None
    installed_by: Optional[str] = None
    org_id: Optional[str] = None  # System level if None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    
    class Config:
        collection = "plugins"
