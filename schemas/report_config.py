from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class ReportBlockSchema(BaseModel):
    """
    Represents a dynamic block configuration in the drag-and-drop structural report builder.
    """

    type: str  # "header", "metric", "rich_text", "chart", "table"
    config: Dict[str, Any] = Field(default_factory=dict)


class ReportConfigCreateSchema(BaseModel):
    """
    Validation schema for creating an automated report.
    """

    name: str = Field(..., min_length=1, max_length=255)
    trigger_type: str = "schedule"  # "schedule" or "threshold"
    cron_expression: Optional[str] = None
    threshold_limit: Optional[int] = None
    blocks: List[ReportBlockSchema] = Field(default_factory=list)
    recipients: List[str] = Field(default_factory=list)
    channels: List[str] = Field(default_factory=lambda: ["storage", "email"])


class ReportConfigUpdateSchema(BaseModel):
    """
    Validation schema for updating report configurations.
    """

    name: Optional[str] = None
    trigger_type: Optional[str] = None
    cron_expression: Optional[str] = None
    threshold_limit: Optional[int] = None
    blocks: Optional[List[ReportBlockSchema]] = None
    recipients: Optional[List[str]] = None
    channels: Optional[List[str]] = None
