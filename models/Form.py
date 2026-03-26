from mongoengine import (
    StringField,
    ListField,
    EmbeddedDocumentField,
    ReferenceField,
    IntField,
    BooleanField,
    DictField,
    DateTimeField,
    ValidationError,
)
from datetime import datetime

from models.enumerations import (
    FIELD_TYPE_CHOICES,
    UI_TYPE_CHOICES,
    STATUS_CHOICES,
    LOGICAL_OPERATOR_CHOICES,
)
from models.base import BaseDocument, BaseEmbeddedDocument, SoftDeleteMixin
from models.components import Condition, Trigger, LogicComponent, UIComponent

# --- Question Specific Components ---


class Option(BaseEmbeddedDocument):
    """Selectable options for Radio/Dropdown fields."""

    description = StringField()
    is_default = BooleanField(default=False)
    is_disabled = BooleanField(default=False)
    option_code = StringField(max_length=100)
    option_label = StringField(max_length=255, required=True)
    option_value = StringField(max_length=255, required=True)
    order = IntField(default=0)
    visibility_condition = EmbeddedDocumentField(Condition)


class MatrixRow(BaseEmbeddedDocument):
    """A row definition for matrix_choice fields."""
    row_label = StringField(required=True)
    row_value = StringField(required=True)
    order = IntField(default=0)
    is_required = BooleanField(default=False)


class ConditionalValidation(BaseEmbeddedDocument):
    """
    Pairs a set of conditions with a specific error message.
    """

    logical_operator = StringField(choices=LOGICAL_OPERATOR_CHOICES, default="AND")
    conditions = ListField(EmbeddedDocumentField(Condition))
    error_message = StringField(required=True)


class Validation(BaseEmbeddedDocument):
    """Rules defining valid data entry for a specific question."""

    is_required = BooleanField(default=False)
    logical_operator = StringField(choices=LOGICAL_OPERATOR_CHOICES, default="AND")
    required_conditions = ListField(EmbeddedDocumentField(Condition))

    # Constraints
    min_length = IntField()
    max_length = IntField()
    min_value = StringField()
    max_value = StringField()
    min_word_count = IntField()
    max_word_count = IntField()

    regex = StringField()
    error_message = StringField()

    # Typed constraints
    date_min = StringField()
    date_max = StringField()
    disable_past_dates = BooleanField(default=False)
    disable_future_dates = BooleanField(default=False)
    disable_weekends = BooleanField(default=False)

    allowed_file_types = ListField(StringField())
    max_files = IntField()
    max_file_size = IntField()

    min_selection = IntField()
    max_selection = IntField()

    is_unique = BooleanField(default=False)
    requires_confirmation = BooleanField(default=False)
    input_mask = StringField()
    custom_validations = ListField(EmbeddedDocumentField(ConditionalValidation))


class QuestionLogic(LogicComponent):
    """Question-specific logic (e.g., derived values)."""

    calculated_value = StringField()


class QuestionUI(UIComponent):
    """Question-specific UI (e.g., hints/placeholders)."""

    placeholder = StringField()
    visible_header = BooleanField(default=False)


class ResponseTemplate(BaseEmbeddedDocument):
    """Templates for data export or notification formatting."""

    name = StringField(required=True)
    description = StringField()
    structure = StringField()
    tags = ListField(StringField())
    meta_data = DictField()


# --- Core Hierarchy Models ---


class Question(BaseEmbeddedDocument):
    """The atomic unit of a form: a single data collection point."""

    label = StringField(required=True)
    field_type = StringField(choices=FIELD_TYPE_CHOICES, required=True)
    help_text = StringField()
    default_value = StringField()
    order = IntField(min_value=0)
    variable_name = StringField(
        regex=r"^[a-zA-Z_][a-zA-Z0-9_]*$",
        help_text="Alphanumeric and underscores only, starting with a letter/underscore.",
    )

    is_repeatable = BooleanField(default=False)
    repeat_min = IntField(default=0)
    repeat_max = IntField()
    keep_last_value = BooleanField(default=False)

    is_hidden = BooleanField(default=False)
    is_read_only = BooleanField(default=False)
    is_sensitive = BooleanField(default=False) # FLE/PII protection

    validation = EmbeddedDocumentField(Validation, default=lambda: Validation())
    logic = EmbeddedDocumentField(QuestionLogic, default=lambda: QuestionLogic())
    ui = EmbeddedDocumentField(QuestionUI, default=lambda: QuestionUI())

    response_templates = ListField(EmbeddedDocumentField(ResponseTemplate))
    options = ListField(EmbeddedDocumentField(Option))
    matrix_rows = ListField(EmbeddedDocumentField(MatrixRow))
    tags = ListField(StringField())
    meta_data = DictField()

    def clean(self):
        v = self.validation
        if v.min_length and v.max_length and v.min_length > v.max_length:
            raise ValidationError("min_length cannot be greater than max_length.")

        if v.date_min and v.date_max:
            try:
                d1 = datetime.fromisoformat(v.date_min)
                d2 = datetime.fromisoformat(v.date_max)
                if d1 > d2:
                    raise ValidationError("date_min cannot be greater than date_max.")
            except (ValueError, TypeError):
                pass

    def refresh_nested_timestamps(self):
        """Recursively updates timestamps for all configuration child documents."""
        self.update_timestamp()
        for doc in [self.validation, self.logic, self.ui]:
            doc.update_timestamp()

        # Update timestamps for all nested validation conditions
        for cond in self.validation.required_conditions:
            cond.update_timestamp()

        for cv in self.validation.custom_validations:
            cv.update_timestamp()
            for cond in cv.conditions:
                cond.update_timestamp()

        for opt in self.options:
            opt.update_timestamp()


class SectionLogic(LogicComponent):
    """Section-specific logic (e.g., group repetition)."""

    is_repeatable = BooleanField(default=False)
    repeat_min = IntField(default=0)
    repeat_max = IntField()


class SectionUI(UIComponent):
    """Section-specific UI (e.g., layout types)."""

    layout_type = StringField(choices=UI_TYPE_CHOICES, default="flex")


class Section(BaseDocument, SoftDeleteMixin):
    """A logical grouping of questions and sub-sections. Extracted to collection to prevent 16MB document limits."""

    meta = {
        "collection": "form_sections",
        "index_background": True,
    }

    title = StringField(required=True)
    description = StringField()
    help_text = StringField()
    order = IntField()

    logic = EmbeddedDocumentField(SectionLogic, default=lambda: SectionLogic())
    ui = EmbeddedDocumentField(SectionUI, default=lambda: SectionUI())

    questions = ListField(EmbeddedDocumentField(Question))
    sections = ListField(ReferenceField("self"))
    response_templates = ListField(EmbeddedDocumentField(ResponseTemplate))
    tags = ListField(StringField())
    meta_data = DictField()

    def clean(self):
        """Validates section structure and depth."""
        self.validate_depth(self, 0)

    @staticmethod
    def validate_depth(section, current_depth):
        MAX_SECTION_DEPTH = 5
        if current_depth > MAX_SECTION_DEPTH:
            raise ValidationError(f"Section depth exceeds maximum limit of {MAX_SECTION_DEPTH}")
        for sub in section.sections:
            Section.validate_depth(sub, current_depth + 1)

    def refresh_nested_timestamps(self):
        """Recursively updates timestamps for the whole section tree."""
        self.update_timestamp()
        self.logic.update_timestamp()
        self.ui.update_timestamp()
        for q in self.questions:
            q.refresh_nested_timestamps()
        for s in self.sections:
            s.refresh_nested_timestamps()


# --- Semantic Versioning & Snapshots ---

# --- Top Level Domain Entities ---


class Form(BaseDocument, SoftDeleteMixin):
    """Main Form entity managing access, publication, and delivery."""

    meta = {
        "collection": "forms",
        "indexes": [
            "slug",
            "status",
            "created_by",
            "active_version",
            "organization_id",
        ],
        "index_background": True,
    }
    title = StringField(max_length=255, required=True, trim=True)
    slug = StringField(
        max_length=255, required=True, unique=True, regex=r"^[a-z0-9-]+$"
    )
    organization_id = StringField(required=True)  # Tenant isolation
    created_by = StringField(required=True)
    status = StringField(choices=STATUS_CHOICES, default="draft")
    ui_type = StringField(choices=UI_TYPE_CHOICES, default="flex")
    active_version = ReferenceField("Version")

    # Metadata & Distribution
    description = StringField()
    help_text = StringField()
    expires_at = DateTimeField()
    publish_at = DateTimeField()
    is_template = BooleanField(default=False)
    is_public = BooleanField(default=False)
    supported_languages = ListField(StringField(), default=["en"])
    default_language = StringField(default="en")
    tags = ListField(StringField())

    # Security & Integration
    editors = ListField(StringField())
    viewers = ListField(StringField())
    submitters = ListField(StringField())
    approval_enabled = BooleanField(default=False)
    style = DictField()
    response_templates = ListField(EmbeddedDocumentField(ResponseTemplate))
    triggers = ListField(EmbeddedDocumentField(Trigger))

    @property
    def is_published(self) -> bool:
        return self.status == "published"

    @property
    def active_version_id(self):
        raw_value = self._data.get("active_version")
        if raw_value is None:
            return None
        return str(getattr(raw_value, "id", raw_value))

    def clean(self):
        if self.publish_at and self.expires_at and self.publish_at > self.expires_at:
            raise ValidationError("publish_at cannot be after expires_at.")


class Project(BaseDocument, SoftDeleteMixin):
    """Container for related Forms and Sub-projects."""

    meta = {
        "collection": "projects",
        "indexes": ["status", "active_version", "tags", "organization_id"],
        "index_background": True,
    }
    title = StringField(max_length=255, required=True, trim=True)
    description = StringField()
    help_text = StringField()
    organization_id = StringField(required=True)  # Tenant isolation
    status = StringField(choices=STATUS_CHOICES, default="draft")
    sub_projects = ListField(ReferenceField("Project"))
    forms = ListField(ReferenceField(Form))
    active_version = ReferenceField("Version")
    tags = ListField(StringField())
    triggers = ListField(EmbeddedDocumentField(Trigger))

    @property
    def active_version_id(self):
        raw_value = self._data.get("active_version")
        if raw_value is None:
            return None
        return str(getattr(raw_value, "id", raw_value))

    def add_sub_project(self, sub_project: "Project") -> None:
        self.sub_projects.append(sub_project)
        self.save()

    def add_form(self, form: Form) -> None:
        self.forms.append(form)
        self.save()


# --- Semantic Versioning & Snapshots ---


class Version(BaseDocument):
    """Semantic versioning (Major.Minor.Patch) for Forms or Projects."""

    meta = {
        "collection": "versions",
        "indexes": [
            "form",
            "project",
            ("-major", "-minor", "-patch"),  # Fast lookup for latest version
        ],
        "index_background": True,
    }
    form = ReferenceField(Form, reverse_delete_rule=2)
    project = ReferenceField("Project", reverse_delete_rule=2)
    major = IntField(default=1, min_value=0)
    minor = IntField(default=0, min_value=0)
    patch = IntField(default=0, min_value=0)

    @property
    def version_string(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def clean(self):
        if not self.form and not self.project:
            raise ValidationError("Either form or project must be provided.")
        if self.form and self.project:
            raise ValidationError(
                "A version cannot be linked to both a form and a project."
            )
        if any(v < 0 for v in (self.major, self.minor, self.patch)):
            raise ValidationError("Version numbers must be non-negative.")


class FormVersion(BaseDocument):
    """Immutable snapshot of form structure at a specific version."""

    meta = {
        "collection": "form_versions",
        "indexes": ["form", "version", "status"],
        "index_background": True,
    }
    form = ReferenceField(Form, required=True, reverse_delete_rule=2)
    version = ReferenceField(Version, required=True)
    sections = ListField(ReferenceField(Section))
    translations = DictField()
    status = StringField(choices=STATUS_CHOICES, default="draft")


class ProjectVersion(BaseDocument):
    """Immutable snapshot of project state at a specific version."""

    meta = {
        "collection": "project_versions",
        "indexes": ["project", "version", "status"],
        "index_background": True,
    }
    project = ReferenceField(Project, required=True, reverse_delete_rule=2)
    version = ReferenceField(Version, required=True)
    forms = ListField(ReferenceField(Form))
    sub_projects = ListField(ReferenceField(Project))
    status = StringField(choices=STATUS_CHOICES, default="draft")
