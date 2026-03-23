from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Any, List
from datetime import datetime


class BaseSchema(BaseModel):
    """Base schema for top-level documents with standard fields."""

    model_config = ConfigDict(
        from_attributes=True, populate_by_name=True, extra="ignore"
    )

    id: Optional[str] = Field(default=None, alias="_id")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SoftDeleteBaseSchema(BaseSchema):
    """Base schema for documents supporting soft delete."""

    is_deleted: bool = False
    deleted_at: Optional[datetime] = None


class InboundPayloadSchema:
    """Schema mixin for rigorous inbound payload constraints."""

    model_config = ConfigDict(extra="ignore")


class BaseEmbeddedSchema(BaseModel):
    """Base schema for embedded documents."""

    model_config = ConfigDict(
        from_attributes=True, populate_by_name=True, extra="ignore"
    )

    id: Optional[str] = Field(default=None, alias="_id")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PaginatedResult(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    has_next: bool
    success: bool = True

    def to_dict(self):
        return self.model_dump()
