from pydantic import Field
from typing import Optional, List, Dict, Any, ForwardRef, Literal
from datetime import datetime

from .base import BaseSchema, BaseEmbeddedSchema, SoftDeleteBaseSchema
from .components import (
    ConditionSchema,
    LogicComponentSchema,
    UIComponentSchema,
    TriggerSchema,
)


class OptionSchema(BaseEmbeddedSchema):
    description: Optional[str] = None
    is_default: bool = False
    is_disabled: bool = False
    option_code: Optional[str] = Field(None, max_length=100)
    option_label: str = Field(..., max_length=255)
    option_value: str = Field(..., max_length=255)
    order: int = 0
    visibility_condition: Optional[ConditionSchema] = None


class MatrixRowSchema(BaseEmbeddedSchema):
    row_label: str = Field(..., max_length=255)
    row_value: str = Field(..., max_length=255)
    order: int = 0
    is_required: bool = False


class ConditionalValidationSchema(BaseEmbeddedSchema):
    logical_operator: str = "AND"
    conditions: List[ConditionSchema] = Field(default_factory=list)
    error_message: str


class ValidationSchema(BaseEmbeddedSchema):
    is_required: bool = False
    logical_operator: str = "AND"
    required_conditions: List[ConditionSchema] = Field(default_factory=list)

    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[str] = None
    max_value: Optional[str] = None
    min_word_count: Optional[int] = None
    max_word_count: Optional[int] = None

    regex: Optional[str] = None
    error_message: Optional[str] = None

    date_min: Optional[str] = None
    date_max: Optional[str] = None
    disable_past_dates: bool = False
    disable_future_dates: bool = False
    disable_weekends: bool = False

    allowed_file_types: List[str] = Field(default_factory=list)
    max_files: Optional[int] = None
    max_file_size: Optional[int] = None
    min_selection: Optional[int] = None
    max_selection: Optional[int] = None

    is_unique: bool = False
    requires_confirmation: bool = False
    input_mask: Optional[str] = None
    custom_validations: List[ConditionalValidationSchema] = Field(default_factory=list)


class QuestionLogicSchema(LogicComponentSchema):
    calculated_value: Optional[str] = None


class QuestionUISchema(UIComponentSchema):
    placeholder: Optional[str] = None
    visible_header: bool = False


class ResponseTemplateSchema(BaseEmbeddedSchema):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    structure: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    meta_data: Optional[Dict[str, Any]] = None


class QuestionSchema(BaseEmbeddedSchema):
    label: str = Field(..., max_length=255)
    field_type: str # Allow all from FIELD_TYPE_CHOICES
    help_text: Optional[str] = None
    default_value: Optional[str] = None
    order: int = Field(default=0, ge=0)
    variable_name: Optional[str] = Field(None, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")

    is_repeatable: bool = False
    repeat_min: int = Field(default=0, ge=0)
    repeat_max: Optional[int] = None
    keep_last_value: bool = False

    is_hidden: bool = False
    is_read_only: bool = False

    validation: Optional[ValidationSchema] = None
    logic: Optional[QuestionLogicSchema] = None
    ui: Optional[QuestionUISchema] = None

    response_templates: List[ResponseTemplateSchema] = Field(default_factory=list)
    options: List[OptionSchema] = Field(default_factory=list)
    matrix_rows: List[MatrixRowSchema] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    meta_data: Optional[Dict[str, Any]] = None


class SectionLogicSchema(LogicComponentSchema):
    is_repeatable: bool = False
    repeat_min: int = Field(default=0, ge=0)
    repeat_max: Optional[int] = None


class SectionUISchema(UIComponentSchema):
    layout_type: str = "flex" # Allow all from UI_TYPE_CHOICES


SectionSchemaStruct = ForwardRef("SectionSchemaStruct")


class SectionSchemaStruct(BaseEmbeddedSchema):
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    help_text: Optional[str] = None
    order: Optional[int] = None

    logic: Optional[SectionLogicSchema] = None
    ui: Optional[SectionUISchema] = None

    questions: List[QuestionSchema] = Field(default_factory=list)
    sections: List["SectionSchemaStruct"] = Field(default_factory=list)
    response_templates: List[ResponseTemplateSchema] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    meta_data: Optional[Dict[str, Any]] = None


SectionSchemaStruct.model_rebuild()
SectionSchema = SectionSchemaStruct


class VersionSchema(BaseSchema):
    form: Optional[str] = None
    project: Optional[str] = None
    major: int = Field(default=1, ge=0)
    minor: int = Field(default=0, ge=0)
    patch: int = Field(default=0, ge=0)
    version_string: Optional[str] = None


class FormVersionSchema(BaseSchema):
    form: str
    version: str
    sections: List[SectionSchema] = Field(default_factory=list)
    translations: Optional[Dict[str, Any]] = None
    status: Literal["draft", "published", "archived"] = "draft"


class ProjectVersionSchema(BaseSchema):
    project: str
    version: str
    forms: List[str] = Field(default_factory=list)
    sub_projects: List[str] = Field(default_factory=list)
    status: Literal["draft", "published", "archived"] = "draft"


class FormSchema(SoftDeleteBaseSchema):
    title: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=255, pattern=r"^[a-z0-9-]+$")
    organization_id: str
    created_by: str
    status: Literal["draft", "published", "archived"] = "draft"
    ui_type: Literal[
        "flex",
        "grid-cols-2",
        "tabbed",
        "custom",
        "grid-cols-3",
        "full-width",
        "cards",
        "card",
    ] = "flex"
    active_version: Optional[str] = None

    description: Optional[str] = None
    help_text: Optional[str] = None
    expires_at: Optional[datetime] = None
    publish_at: Optional[datetime] = None
    is_template: bool = False
    is_public: bool = False
    supported_languages: List[str] = ["en"]
    default_language: str = "en"
    tags: List[str] = Field(default_factory=list)

    editors: List[str] = Field(default_factory=list)
    viewers: List[str] = Field(default_factory=list)
    submitters: List[str] = Field(default_factory=list)
    approval_enabled: bool = False
    style: Optional[Dict[str, Any]] = None
    response_templates: List[ResponseTemplateSchema] = Field(default_factory=list)
    triggers: List[TriggerSchema] = Field(default_factory=list)


class ProjectSchema(SoftDeleteBaseSchema):
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    help_text: Optional[str] = None
    organization_id: str
    status: Literal["draft", "published", "archived"] = "draft"
    sub_projects: List[str] = Field(default_factory=list)
    forms: List[str] = Field(default_factory=list)
    active_version: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    triggers: List[TriggerSchema] = Field(default_factory=list)
