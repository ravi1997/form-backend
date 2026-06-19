"""
schemas/common_schemas.py
Common request/response schemas used across multiple endpoints.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any, Generic, TypeVar
from datetime import datetime
from enum import Enum


class SortOrder(str, Enum):
    """Sort order enumeration."""
    ASC = "asc"
    DESC = "desc"


class SortField(BaseModel):
    """Sort field schema."""
    field: str = Field(..., description="Field name to sort by")
    order: SortOrder = Field(default=SortOrder.ASC, description="Sort order")


class FilterOperator(str, Enum):
    """Filter operator enumeration."""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_THAN_EQUALS = "greater_than_equals"
    LESS_THAN_EQUALS = "less_than_equals"
    IN_LIST = "in_list"
    NOT_IN_LIST = "not_in_list"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"


class FilterCondition(BaseModel):
    """Filter condition schema."""
    field: str = Field(..., description="Field name to filter")
    operator: FilterOperator = Field(..., description="Filter operator")
    value: Any = Field(None, description="Filter value")
    values: List[Any] = Field(default=[], description="Filter values (for IN_LIST operators)")


class PaginationParams(BaseModel):
    """Pagination parameters schema."""
    page: int = Field(default=1, ge=1, description="Page number")
    per_page: int = Field(default=20, ge=1, le=100, description="Items per page")


class SortParams(BaseModel):
    """Sort parameters schema."""
    sort_by: List[SortField] = Field(default=[], description="Sort fields")
    default_sort: List[SortField] = Field(default=[], description="Default sort fields")


class SearchParams(BaseModel):
    """Search parameters schema."""
    query: Optional[str] = Field(None, description="Search query")
    search_fields: List[str] = Field(default=[], description="Fields to search in")


class FilterParams(BaseModel):
    """Filter parameters schema."""
    filters: List[FilterCondition] = Field(default=[], description="Filter conditions")


class ListRequest(BaseModel):
    """Generic list request schema."""
    pagination: PaginationParams = Field(default_factory=PaginationParams, description="Pagination parameters")
    sort: SortParams = Field(default_factory=SortParams, description="Sort parameters")
    search: SearchParams = Field(default_factory=SearchParams, description="Search parameters")
    filter: FilterParams = Field(default_factory=FilterParams, description="Filter parameters")


class PaginationResponse(BaseModel):
    """Pagination response schema."""
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Items per page")
    total_items: int = Field(..., description="Total number of items")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Has next page")
    has_prev: bool = Field(..., description="Has previous page")


class ErrorResponse(BaseModel):
    """Error response schema."""
    error: str = Field(..., description="Error message")
    error_code: str = Field(..., description="Error code")
    details: Optional[Dict[str, Any]] = Field(None, description="Error details")


class SuccessResponse(BaseModel):
    """Success response schema."""
    message: str = Field(..., description="Success message")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data")


class HealthCheckResponse(BaseModel):
    """Health check response schema."""
    status: str = Field(..., description="Service status")
    timestamp: datetime = Field(..., description="Check timestamp")
    version: str = Field(..., description="Service version")
    database: str = Field(..., description="Database status")
    cache: str = Field(..., description="Cache status")


T = TypeVar('T')


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response schema."""
    data: List[T] = Field(..., description="List of items")
    pagination: PaginationResponse = Field(..., description="Pagination information")


class FileUploadResponse(BaseModel):
    """File upload response schema."""
    id: str = Field(..., description="File ID")
    filename: str = Field(..., description="Original filename")
    file_size: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="File MIME type")
    upload_url: Optional[str] = Field(None, description="Upload URL")
    download_url: Optional[str] = Field(None, description="Download URL")
    created_at: datetime = Field(..., description="Upload timestamp")