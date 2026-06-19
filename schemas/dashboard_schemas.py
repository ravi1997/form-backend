"""
schemas/dashboard_schemas.py
Dashboard-related request/response schemas.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class DashboardStatus(str, Enum):
    """Dashboard status enumeration."""
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class WidgetType(str, Enum):
    """Dashboard widget type enumeration."""
    KPI = "kpi"
    CHART = "chart"
    TABLE = "table"
    TEXT = "text"
    IMAGE = "image"
    FILTER = "filter"


class FilterType(str, Enum):
    """Dashboard filter type enumeration."""
    DATE_RANGE = "date_range"
    TEXT_SELECT = "text_select"
    MULTI_SELECT = "multi_select"
    NUMBER_RANGE = "number_range"


class DashboardWidgetSchema(BaseModel):
    """Dashboard widget schema."""
    id: str = Field(..., description="Widget ID")
    widget_type: WidgetType = Field(..., description="Widget type")
    title: Optional[str] = Field(None, description="Widget title")
    description: Optional[str] = Field(None, description="Widget description")
    position: Dict[str, Any] = Field(..., description="Widget position (x, y, width, height)")
    config: Dict[str, Any] = Field(default={}, description="Widget configuration")
    data_source: Dict[str, Any] = Field(default={}, description="Data source configuration")
    refresh_interval: Optional[int] = Field(None, description="Refresh interval in seconds")
    is_visible: bool = Field(default=True, description="Is widget visible")


class DashboardFilterSchema(BaseModel):
    """Dashboard filter schema."""
    id: str = Field(..., description="Filter ID")
    name: str = Field(..., description="Filter name")
    filter_type: FilterType = Field(..., description="Filter type")
    field_name: str = Field(..., description="Field name to filter")
    options: List[Dict[str, Any]] = Field(default=[], description="Filter options")
    default_value: Optional[str] = Field(None, description="Default filter value")
    is_required: bool = Field(default=False, description="Is filter required")


class DashboardCreateRequest(BaseModel):
    """Dashboard creation request schema."""
    name: str = Field(..., min_length=1, max_length=200, description="Dashboard name")
    description: Optional[str] = Field(None, max_length=1000, description="Dashboard description")
    widgets: List[DashboardWidgetSchema] = Field(..., min_items=1, description="Dashboard widgets")
    filters: List[DashboardFilterSchema] = Field(default=[], description="Dashboard filters")
    layout: Dict[str, Any] = Field(default={}, description="Dashboard layout configuration")
    theme: Dict[str, Any] = Field(default={}, description="Dashboard theme settings")
    is_public: bool = Field(default=False, description="Is public dashboard")
    auto_refresh: bool = Field(default=False, description="Auto-refresh dashboard")
    refresh_interval: int = Field(default=300, description="Refresh interval in seconds")


class DashboardUpdateRequest(BaseModel):
    """Dashboard update request schema."""
    name: Optional[str] = Field(None, min_length=1, max_length=200, description="Dashboard name")
    description: Optional[str] = Field(None, max_length=1000, description="Dashboard description")
    widgets: Optional[List[DashboardWidgetSchema]] = Field(None, min_items=1, description="Dashboard widgets")
    filters: Optional[List[DashboardFilterSchema]] = Field(None, description="Dashboard filters")
    layout: Optional[Dict[str, Any]] = Field(None, description="Dashboard layout configuration")
    theme: Optional[Dict[str, Any]] = Field(None, description="Dashboard theme settings")
    status: Optional[DashboardStatus] = Field(None, description="Dashboard status")
    is_public: Optional[bool] = Field(None, description="Is public dashboard")
    auto_refresh: Optional[bool] = Field(None, description="Auto-refresh dashboard")
    refresh_interval: Optional[int] = Field(None, description="Refresh interval in seconds")


class DashboardResponse(BaseModel):
    """Dashboard response schema."""
    id: str = Field(..., description="Dashboard ID")
    name: str = Field(..., description="Dashboard name")
    description: Optional[str] = Field(None, description="Dashboard description")
    status: DashboardStatus = Field(..., description="Dashboard status")
    widget_count: int = Field(..., description="Number of widgets")
    filter_count: int = Field(..., description="Number of filters")
    is_public: bool = Field(..., description="Is public dashboard")
    auto_refresh: bool = Field(..., description="Auto-refresh enabled")
    refresh_interval: int = Field(..., description="Refresh interval in seconds")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Update timestamp")


class DashboardSnapshotRequest(BaseModel):
    """Dashboard snapshot request schema."""
    dashboard_id: str = Field(..., description="Dashboard ID")
    name: str = Field(..., min_length=1, max_length=200, description="Snapshot name")
    description: Optional[str] = Field(None, max_length=1000, description="Snapshot description")


class DashboardSnapshotResponse(BaseModel):
    """Dashboard snapshot response schema."""
    id: str = Field(..., description="Snapshot ID")
    dashboard_id: str = Field(..., description="Dashboard ID")
    name: str = Field(..., description="Snapshot name")
    description: Optional[str] = Field(None, description="Snapshot description")
    created_at: datetime = Field(..., description="Creation timestamp")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp")