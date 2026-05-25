from pydantic import BaseModel, Field
from typing import Literal, Optional, Any, Dict


class TaskStatusSchema(BaseModel):
    """Schema for task status response."""

    task_id: str = Field(..., description="Celery task ID")
    state: Literal["PENDING", "STARTED", "SUCCESS", "FAILURE", "RETRY", "REVOKED"] = (
        Field(..., description="Task state")
    )
    result: Optional[Dict[str, Any]] = Field(
        None, description="Task result (if successful)"
    )
    error: Optional[str] = Field(None, description="Error message (if failed)")
    traceback: Optional[str] = Field(None, description="Error traceback (if failed)")
    current_progress: Optional[int] = Field(
        None, description="Current progress percentage (if available)"
    )
    total_progress: Optional[int] = Field(
        None, description="Total progress (if available)"
    )


class TaskStatusOutSchema(TaskStatusSchema):
    """Explicitly named schema for task status output alignment."""
    pass


class TaskCreateSchema(BaseModel):
    """Schema for task creation request."""

    task_name: str = Field(..., description="Celery task name")
    args: Optional[list] = Field(default_factory=list, description="Task arguments")
    kwargs: Optional[dict] = Field(
        default_factory=dict, description="Task keyword arguments"
    )
    options: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Celery task options (queue, routing_key, etc.)",
    )
