"""
schemas/form_schemas.py
Form-related request/response schemas.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class FieldType(str, Enum):
    """Form field type enumeration."""
    INPUT = "input"
    TEXTAREA = "textarea"
    NUMBER = "number"
    EMAIL = "email"
    MOBILE = "mobile"
    URL = "url"
    PASSWORD = "password"
    SELECT = "select"
    DROPDOWN = "dropdown"
    RADIO = "radio"
    CHECKBOX = "checkbox"
    MULTI_SELECT = "multi_select"
    DATE = "date"
    TIME = "time"
    DATETIME = "datetime"
    FILE_UPLOAD = "file_upload"
    SIGNATURE = "signature"


class FormStatus(str, Enum):
    """Form status enumeration."""
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class UIType(str, Enum):
    """Form UI type enumeration."""
    FLEX = "flex"
    GRID_COLS_2 = "grid-cols-2"
    TABBED = "tabbed"
    CUSTOM = "custom"
    WIZARD = "wizard"


class OptionSchema(BaseModel):
    """Form field option schema."""
    value: str = Field(..., description="Option value")
    label: str = Field(..., description="Option label")
    is_default: bool = Field(default=False, description="Is default option")
    order: int = Field(default=0, description="Display order")


class QuestionSchema(BaseModel):
    """Form question schema."""
    id: str = Field(..., description="Question ID")
    name: str = Field(..., description="Question name")
    label: str = Field(..., description="Question label")
    field_type: FieldType = Field(..., description="Field type")
    required: bool = Field(default=False, description="Is required")
    placeholder: Optional[str] = Field(None, description="Placeholder text")
    description: Optional[str] = Field(None, description="Description")
    default_value: Optional[str] = Field(None, description="Default value")
    options: List[OptionSchema] = Field(default=[], description="Select options")
    order: int = Field(default=0, description="Display order")
    validation: Dict[str, Any] = Field(default={}, description="Validation rules")


class SectionSchema(BaseModel):
    """Form section schema."""
    id: str = Field(..., description="Section ID")
    name: str = Field(..., description="Section name")
    title: str = Field(..., description="Section title")
    description: Optional[str] = Field(None, description="Section description")
    order: int = Field(default=0, description="Display order")
    questions: List[QuestionSchema] = Field(default=[], description="Section questions")
    subsections: List['SectionSchema'] = Field(default=[], description="Subsections")


class FormCreateRequest(BaseModel):
    """Form creation request schema."""
    name: str = Field(..., min_length=1, max_length=200, description="Form name")
    description: Optional[str] = Field(None, max_length=1000, description="Form description")
    ui_type: UIType = Field(default=UIType.FLEX, description="UI type")
    sections: List[SectionSchema] = Field(..., min_items=1, description="Form sections")
    tags: List[str] = Field(default=[], description="Form tags")
    is_public: bool = Field(default=False, description="Is public form")
    allow_anonymous: bool = Field(default=False, description="Allow anonymous submissions")
    require_login: bool = Field(default=True, description="Require login to submit")


class FormUpdateRequest(BaseModel):
    """Form update request schema."""
    name: Optional[str] = Field(None, min_length=1, max_length=200, description="Form name")
    description: Optional[str] = Field(None, max_length=1000, description="Form description")
    ui_type: Optional[UIType] = Field(None, description="UI type")
    sections: Optional[List[SectionSchema]] = Field(None, min_items=1, description="Form sections")
    status: Optional[FormStatus] = Field(None, description="Form status")
    tags: Optional[List[str]] = Field(None, description="Form tags")
    is_public: Optional[bool] = Field(None, description="Is public form")
    allow_anonymous: Optional[bool] = Field(None, description="Allow anonymous submissions")
    require_login: Optional[bool] = Field(None, description="Require login to submit")


class FormResponse(BaseModel):
    """Form response schema."""
    id: str = Field(..., description="Form ID")
    name: str = Field(..., description="Form name")
    description: Optional[str] = Field(None, description="Form description")
    status: FormStatus = Field(..., description="Form status")
    ui_type: UIType = Field(..., description="UI type")
    sections: List[SectionSchema] = Field(..., description="Form sections")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Update timestamp")


class FormSubmissionRequest(BaseModel):
    """Form submission request schema."""
    form_id: str = Field(..., description="Form ID")
    answers: Dict[str, Any] = Field(..., description="Question answers")
    repeat_groups: Dict[str, List[Dict[str, Any]]] = Field(default={}, description="Repeated section answers")
    respondent_email: Optional[str] = Field(None, description="Respondent email (for anonymous)")


class FormSubmissionResponse(BaseModel):
    """Form submission response schema."""
    id: str = Field(..., description="Response ID")
    form_id: str = Field(..., description="Form ID")
    status: str = Field(..., description="Submission status")
    submission_number: int = Field(..., description="Submission number")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    time_taken_seconds: Optional[int] = Field(None, description="Time taken in seconds")