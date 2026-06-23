import re
from pydantic import Field, model_validator
from typing import Optional, List, Dict, Any, ForwardRef, Literal
from datetime import datetime
from urllib.parse import urlparse

from .base import BaseSchema, BaseEmbeddedSchema, SoftDeleteBaseSchema
from .components import (
    ConditionSchema,
    LogicComponentSchema,
    UIComponentSchema,
    TriggerSchema,
)
from .taxonomy import TaxonomyItemSchema


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

    min_length: Optional[int] = Field(default=None, alias="minLength")
    max_length: Optional[int] = Field(default=None, alias="maxLength")
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


class QuickResponseSchema(BaseEmbeddedSchema):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    visibility: Literal["personal", "project", "org"] = "personal"
    owner_id: Optional[str] = Field(default=None, alias="ownerId")
    field_values: Dict[str, Any] = Field(default_factory=dict, alias="fieldValues")
    is_archived: bool = Field(default=False, alias="isArchived")

    @model_validator(mode="after")
    def normalize(self):
        self.name = (self.name or "").strip()
        if not self.name:
            raise ValueError("name is required for quick responses.")
        self.description = (self.description or "").strip() or None
        self.visibility = str(self.visibility or "personal").strip().lower()
        if self.visibility not in {"personal", "project", "org"}:
            raise ValueError("visibility must be personal, project, or org.")
        tags: List[str] = []
        seen = set()
        for tag in self.tags or []:
            text = str(tag).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            tags.append(text)
        self.tags = tags
        if not isinstance(self.field_values, dict):
            raise ValueError("field_values must be an object of key/value pairs.")
        self.field_values = {
            str(key).strip(): value
            for key, value in self.field_values.items()
            if str(key).strip()
        }
        return self


class CsvExportDefaultsSchema(BaseEmbeddedSchema):
    delimiter: str = Field(default=",", max_length=1)
    header_mode: Literal["labels", "keys"] = Field(default="labels", alias="headerMode")
    empty_field_value: str = Field(default="", alias="emptyFieldValue")
    date_format: str = Field(default="iso8601", alias="dateFormat")
    timezone: str = Field(default="UTC")
    encoding: str = Field(default="utf-8")
    include_attachments: bool = Field(default=False, alias="includeAttachments")

    @model_validator(mode="after")
    def normalize(self):
        delimiter = (self.delimiter or ",").strip() or ","
        if len(delimiter) != 1:
            raise ValueError("CSV delimiter must be a single character.")
        self.delimiter = delimiter

        header_mode = str(self.header_mode or "labels").strip().lower()
        if header_mode not in {"labels", "keys"}:
            raise ValueError("header_mode must be either 'labels' or 'keys'.")
        self.header_mode = header_mode

        self.empty_field_value = (self.empty_field_value or "").strip()
        self.date_format = (self.date_format or "iso8601").strip() or "iso8601"
        self.timezone = (self.timezone or "UTC").strip() or "UTC"
        self.encoding = (self.encoding or "utf-8").strip() or "utf-8"
        return self


class DataAnonymizationSchema(BaseEmbeddedSchema):
    mode: Literal["none", "mask", "remove", "hash"] = "none"
    fields: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize(self):
        mode = str(self.mode or "none").strip().lower()
        if mode not in {"none", "mask", "remove", "hash"}:
            raise ValueError("anonymization.mode must be one of: none, mask, remove, hash.")
        self.mode = mode

        fields: List[str] = []
        seen = set()
        for field in self.fields or []:
            text = str(field).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            fields.append(text)
        self.fields = fields
        return self


class DataExportSettingsSchema(BaseEmbeddedSchema):
    csv_defaults: CsvExportDefaultsSchema = Field(
        default_factory=CsvExportDefaultsSchema,
        alias="csvDefaults",
    )
    retention_days: Optional[int] = Field(default=None, ge=0, alias="retentionDays")
    field_mapping: Dict[str, str] = Field(default_factory=dict, alias="fieldMapping")
    anonymization: DataAnonymizationSchema = Field(
        default_factory=DataAnonymizationSchema
    )

    @model_validator(mode="after")
    def normalize(self):
        if self.retention_days is not None and self.retention_days < 0:
            raise ValueError("retention_days must be a non-negative integer.")

        normalized_mapping: Dict[str, str] = {}
        seen_aliases = set()
        mapping = self.field_mapping or {}
        if not isinstance(mapping, dict):
            raise ValueError("field_mapping must be an object of string values.")
        for key, value in mapping.items():
            field_key = str(key).strip()
            field_value = str(value).strip()
            if not field_key or not field_value:
                continue
            if field_value in seen_aliases:
                raise ValueError("field_mapping values must be unique.")
            seen_aliases.add(field_value)
            normalized_mapping[field_key] = field_value
        self.field_mapping = normalized_mapping
        return self


class AdvancedSettingsSchema(BaseEmbeddedSchema):
    slug: Optional[str] = Field(default=None, max_length=255)
    internal_code: Optional[str] = Field(
        default=None, max_length=120, alias="internalCode"
    )
    locale_default: Optional[str] = Field(
        default=None, max_length=32, alias="localeDefault"
    )
    fallback_language: Optional[str] = Field(
        default=None, max_length=32, alias="fallbackLanguage"
    )
    api_identifiers: Dict[str, str] = Field(
        default_factory=dict, alias="apiIdentifiers"
    )
    experimental_flags: Dict[str, bool] = Field(
        default_factory=dict, alias="experimentalFlags"
    )

    @model_validator(mode="after")
    def normalize_and_validate(self):
        if isinstance(self.slug, str):
            self.slug = self.slug.strip().lower() or None
            if self.slug and not re.fullmatch(r"^[a-z0-9-]+$", self.slug):
                raise ValueError(
                    "slug must contain only lowercase letters, numbers, and hyphens."
                )

        if isinstance(self.internal_code, str):
            self.internal_code = self.internal_code.strip() or None
            if self.internal_code and not re.fullmatch(r"^[A-Za-z0-9_-]+$", self.internal_code):
                raise ValueError(
                    "internal_code must contain only letters, numbers, underscores, and hyphens."
                )

        def _normalize_locale(value: Optional[str]) -> Optional[str]:
            if not isinstance(value, str):
                return None
            text = value.strip().replace("_", "-")
            if not text:
                return None
            parts = text.split("-")
            if len(parts) == 1:
                return parts[0].lower()
            head = parts[0].lower()
            tail = []
            for idx, part in enumerate(parts[1:], start=1):
                if idx == 1 and len(part) == 2:
                    tail.append(part.upper())
                else:
                    tail.append(part.lower())
            return "-".join([head, *tail])

        self.locale_default = _normalize_locale(self.locale_default)
        self.fallback_language = _normalize_locale(self.fallback_language)
        if self.fallback_language is None:
            self.fallback_language = self.locale_default

        if self.api_identifiers is None:
            self.api_identifiers = {}
        if not isinstance(self.api_identifiers, dict):
            raise ValueError("api_identifiers must be an object of string keys.")
        normalized_identifiers: Dict[str, str] = {}
        for key, value in self.api_identifiers.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("api_identifiers keys must be non-empty strings.")
            if value is None:
                continue
            if not isinstance(value, str):
                raise ValueError("api_identifiers values must be strings.")
            normalized_identifiers[key.strip()] = value.strip()
        self.api_identifiers = normalized_identifiers

        if self.experimental_flags is None:
            self.experimental_flags = {}
        if not isinstance(self.experimental_flags, dict):
            raise ValueError("experimental_flags must be an object of boolean values.")
        normalized_flags: Dict[str, bool] = {}
        for key, value in self.experimental_flags.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("experimental_flags keys must be non-empty strings.")
            if not isinstance(value, bool):
                raise ValueError("experimental_flags values must be boolean.")
            normalized_flags[key.strip()] = value
        self.experimental_flags = normalized_flags

        return self


class SubmissionSettingsSchema(BaseEmbeddedSchema):
    confirmation_message: Optional[str] = Field(default=None, max_length=1000)
    redirect_after_submit: bool = False
    redirect_url: Optional[str] = Field(default=None, max_length=2048)
    allow_multiple_submissions: bool = False
    save_and_resume: bool = False
    draft_handling: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def normalize_and_validate(self):
        if isinstance(self.confirmation_message, str):
            self.confirmation_message = self.confirmation_message.strip() or None

        if self.redirect_after_submit:
            if not self.redirect_url:
                raise ValueError(
                    "redirect_url is required when redirect_after_submit is enabled."
                )
            parsed = urlparse(str(self.redirect_url))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("redirect_url must be a valid http or https URL.")
        else:
            self.redirect_url = None

        if not self.save_and_resume:
            self.draft_handling = None

        return self


class QuestionSchema(BaseEmbeddedSchema):
    label: str = Field(..., max_length=255)
    field_type: str = Field(..., alias="fieldType")  # Allow all from FIELD_TYPE_CHOICES
    help_text: Optional[str] = Field(default=None, alias="helpText")
    default_value: Optional[str] = Field(default=None, alias="defaultValue")
    order: int = Field(default=0, ge=0)
    variable_name: Optional[str] = Field(
        None, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$", alias="variableName"
    )

    is_repeatable: bool = Field(default=False, alias="isRepeatable")
    repeat_min: int = Field(default=0, ge=0, alias="repeatMin")
    repeat_max: Optional[int] = Field(default=None, alias="repeatMax")
    keep_last_value: bool = Field(default=False, alias="keepLastValue")

    is_hidden: bool = Field(default=False, alias="isHidden")
    is_read_only: bool = Field(default=False, alias="isReadOnly")

    validation: Optional[ValidationSchema] = None
    logic: Optional[QuestionLogicSchema] = None
    ui: Optional[QuestionUISchema] = None

    response_templates: List[ResponseTemplateSchema] = Field(default_factory=list)
    options: List[OptionSchema] = Field(default_factory=list)
    matrix_rows: List[MatrixRowSchema] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    meta_data: Optional[Dict[str, Any]] = None


class SectionLogicSchema(LogicComponentSchema):
    is_repeatable: bool = Field(default=False, alias="isRepeatable")
    repeat_min: int = Field(default=0, ge=0, alias="repeatMin")
    repeat_max: Optional[int] = Field(default=None, alias="repeatMax")


class SectionUISchema(UIComponentSchema):
    # Legacy compatibility only. `SectionSchemaStruct.layout` is the
    # canonical internal section layout field.
    layout_type: Optional[str] = None


SectionSchemaStruct = ForwardRef("SectionSchemaStruct")


class SectionSchemaStruct(BaseEmbeddedSchema):
    title: str = Field(..., max_length=255)
    description: Optional[str] = Field(default=None, alias="description")
    help_text: Optional[str] = Field(default=None, alias="helpText")
    order: Optional[int] = None
    layout: str = Field(
        default="standard",
        description="Canonical section-internal layout for questions and nested sub-sections.",
    )
    grid_columns: int = Field(default=2, alias="gridColumns")
    is_hidden: bool = Field(default=False, alias="isHidden")
    is_repeatable: bool = Field(default=False, alias="isRepeatable")
    repeat_min: Optional[int] = Field(default=None, alias="repeatMin")
    repeat_max: Optional[int] = Field(default=None, alias="repeatMax")
    conditional_logic: Optional[Dict[str, Any]] = None
    style: Optional[Dict[str, Any]] = None

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
    access_policy: Optional[Dict[str, Any]] = None
    submission_settings: Optional[SubmissionSettingsSchema] = None
    quick_responses: List[QuickResponseSchema] = Field(
        default_factory=list,
        alias="quickResponses",
    )
    data_export_settings: Optional[DataExportSettingsSchema] = Field(
        default_factory=DataExportSettingsSchema,
        alias="dataExportSettings",
    )
    advanced_settings: Optional[AdvancedSettingsSchema] = Field(
        default=None, alias="advancedSettings"
    )
    status: Literal["draft", "published", "archived"] = "draft"
    classification_enabled: bool = False
    classification_taxonomy: List[TaxonomyItemSchema] = Field(default_factory=list)


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
    project: Optional[str] = None
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
    workflows: Optional[Dict[str, Any]] = None
    access_policy: Optional[Dict[str, Any]] = None
    submission_settings: Optional[SubmissionSettingsSchema] = None
    quick_responses: List[QuickResponseSchema] = Field(
        default_factory=list,
        alias="quickResponses",
    )
    data_export_settings: Optional[DataExportSettingsSchema] = Field(
        default_factory=DataExportSettingsSchema,
        alias="dataExportSettings",
    )
    advanced_settings: Optional[AdvancedSettingsSchema] = Field(
        default=None, alias="advancedSettings"
    )
    response_templates: List[ResponseTemplateSchema] = Field(default_factory=list)
    triggers: List[TriggerSchema] = Field(default_factory=list)
    sections: List[SectionSchema] = Field(
        default_factory=list,
        description="Optional canvas-sync section tree. Form-wide layout remains `ui_type`.",
    )
    classification_enabled: bool = False
    classification_taxonomy: List[TaxonomyItemSchema] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_advanced_settings_input(cls, data):
        if not isinstance(data, dict):
            return data

        payload = data.get("advanced_settings", data.get("advancedSettings"))
        if isinstance(payload, dict):
            payload_model = AdvancedSettingsSchema.model_validate(payload)
            if payload_model.slug:
                data["slug"] = payload_model.slug
            if payload_model.locale_default:
                data["default_language"] = payload_model.locale_default
        return data

    @model_validator(mode="after")
    def sync_advanced_settings_fields(self):
        if getattr(self, "advanced_settings", None):
            if getattr(self.advanced_settings, "slug", None):
                self.slug = self.advanced_settings.slug
            if getattr(self.advanced_settings, "locale_default", None):
                self.default_language = self.advanced_settings.locale_default
        return self


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

    @model_validator(mode="before")
    @classmethod
    def normalize_title_input(cls, data):
        if not isinstance(data, dict):
            return data
        if "title" not in data and "name" in data:
            data["title"] = data.get("name")
        return data
