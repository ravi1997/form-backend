"""
models/form.py
Form and form-related models: Form, Section, Question, Version, Template.
"""

from mongoengine import (
    StringField, ListField, EmbeddedDocumentField, ReferenceField, DictField,
    BooleanField, DateTimeField, IntField, EmbeddedDocument, ValidationError
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument
from models.components import Condition, Trigger, LogicComponent, UIComponent

# Import choice constants
from models.base import (
    FIELD_TYPE_CHOICES, STATUS_CHOICES, UI_TYPE_CHOICES, FIELD_API_CALL_CHOICES,
    TRIGGER_EVENT_CHOICES, TRIGGER_ACTION_CHOICES
)


class QuickResponse(BaseEmbeddedDocument):
    """Reusable quick-fill preset for response drafting."""

    name = StringField(required=True, max_length=255)
    description = StringField()
    tags = ListField(StringField(), default=list)
    visibility = StringField(choices=["personal", "project", "org"], default="personal")
    owner_id = StringField()
    field_values = DictField(default=dict)
    is_archived = BooleanField(default=False)


def default_data_export_settings():
    return {
        "csv_defaults": {
            "delimiter": ",",
            "header_mode": "labels",
            "empty_field_value": "",
            "date_format": "iso8601",
            "timezone": "UTC",
            "encoding": "utf-8",
            "include_attachments": False,
        },
        "retention_days": None,
        "field_mapping": {},
        "anonymization": {
            "mode": "none",
            "fields": [],
        },
    }


class Option(BaseEmbeddedDocument):
    """Selectable options for Radio/Dropdown fields."""

    description = StringField()
    value = StringField(required=True)
    label = StringField(required=True)
    is_default = BooleanField(default=False)
    order = IntField(default=0)
    meta_data = DictField()


class Question(LogicComponent, UIComponent):
    """Individual form field with rich configuration."""

    meta = {"allow_inheritance": True}
    
    id = StringField(required=True)
    name = StringField(required=True)
    label = StringField(required=True)
    field_type = StringField(required=True, choices=FIELD_TYPE_CHOICES)
    required = BooleanField(default=False)
    placeholder = StringField()
    description = StringField()
    default_value = StringField()
    validation = DictField()
    options = ListField(EmbeddedDocumentField(Option))
    order = IntField(default=0)
    repeatable = BooleanField(default=False)
    repeat_label = StringField()
    max_repeats = IntField()
    ui_component = StringField()
    ui_props = DictField()
    data_source = DictField()
    api_endpoint = StringField()
    dependent_questions = ListField(StringField())
    conditional_display = DictField()
    triggers = ListField(EmbeddedDocumentField(Trigger))
    meta_data = DictField()


class Section(LogicComponent, UIComponent):
    """Form section containing questions and subsections."""

    id = StringField(required=True)
    name = StringField(required=True)
    title = StringField(required=True)
    description = StringField()
    order = IntField(default=0)
    repeatable = BooleanField(default=False)
    repeat_label = StringField()
    max_repeats = IntField()
    questions = ListField(EmbeddedDocumentField(Question))
    subsections = ListField(EmbeddedDocumentField("self"))
    ui_component = StringField()
    ui_props = DictField()
    triggers = ListField(EmbeddedDocumentField(Trigger))
    meta_data = DictField()


class FormVersion(BaseEmbeddedDocument):
    """Version control for form schema changes."""

    version_id = StringField(required=True)
    version_number = StringField(required=True)
    version_name = StringField()
    version_description = StringField()
    created_at = DateTimeField()
    created_by = StringField()
    is_current = BooleanField(default=False)
    schema = DictField()
    ui_config = DictField()
    meta_data = DictField()


class Form(BaseDocument, SoftDeleteMixin):
    """Main form model with versioning and access control."""

    meta = {
        "collection": "forms",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            {"fields": ["organization_id", "slug"], "unique": True, "sparse": True},
            "organization_id",
            "status",
            "created_by",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    slug = StringField(trim=True)
    description = StringField()
    status = StringField(choices=STATUS_CHOICES, default="draft")
    ui_type = StringField(choices=UI_TYPE_CHOICES, default="flex")
    ui_config = DictField()
    sections = ListField(EmbeddedDocumentField(Section))
    versions = ListField(EmbeddedDocumentField(FormVersion))
    current_version = StringField()
    created_by = ReferenceField("User", reverse_delete_rule=3)
    owner = ReferenceField("User", reverse_delete_rule=3)
    collaborators = ListField(ReferenceField("User"))
    tags = ListField(StringField())
    is_public = BooleanField(default=False)
    allow_anonymous = BooleanField(default=False)
    require_login = BooleanField(default=True)
    max_submissions = IntField()
    expires_at = DateTimeField()
    data_export_settings = DictField(default=default_data_export_settings)
    triggers = ListField(EmbeddedDocumentField(Trigger))
    meta_data = DictField()

    def clean(self):
        # Ensure at least one section exists
        if not self.sections:
            raise ValidationError("Form must have at least one section.")
        
        # Validate section IDs are unique
        section_ids = [section.id for section in self.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValidationError("Section IDs must be unique within a form.")
        
        # Validate question IDs are unique within each section
        for section in self.sections:
            question_ids = [question.id for question in section.questions]
            if len(question_ids) != len(set(question_ids)):
                raise ValidationError(f"Question IDs must be unique within section '{section.id}'.")


class FormTemplate(BaseDocument, SoftDeleteMixin):
    """Reusable form templates."""

    meta = {
        "collection": "form_templates",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            "organization_id",
            "is_public",
            "category",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    description = StringField()
    category = StringField()
    tags = ListField(StringField())
    is_public = BooleanField(default=False)
    is_system = BooleanField(default=False)
    schema = DictField()  # Form schema that can be used to create new forms
    created_by = ReferenceField("User", reverse_delete_rule=3)
    usage_count = IntField(default=0)
    meta_data = DictField()


class Project(BaseDocument, SoftDeleteMixin):
    """Project container for forms and related resources."""

    meta = {
        "collection": "projects",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            {"fields": ["organization_id", "slug"], "unique": True, "sparse": True},
            "organization_id",
            "status",
            "created_by",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    slug = StringField(trim=True)
    description = StringField()
    status = StringField(choices=STATUS_CHOICES, default="draft")
    forms = ListField(ReferenceField(Form, reverse_delete_rule=3))
    created_by = ReferenceField("User", reverse_delete_rule=3)
    owner = ReferenceField("User", reverse_delete_rule=3)
    collaborators = ListField(ReferenceField("User"))
    tags = ListField(StringField())
    is_public = BooleanField(default=False)
    meta_data = DictField()


class FormBlueprint(BaseDocument, SoftDeleteMixin):
    """Blueprint for creating forms with predefined structure."""

    meta = {
        "collection": "form_blueprints",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            "organization_id",
            "category",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    description = StringField()
    category = StringField()
    version = StringField(default="1.0")
    schema = DictField()  # Blueprint schema
    parameters = DictField()  # Configurable parameters
    created_by = ReferenceField("User", reverse_delete_rule=3)
    is_public = BooleanField(default=False)
    is_system = BooleanField(default=False)
    meta_data = DictField()


class ProjectBlueprint(BaseDocument, SoftDeleteMixin):
    """Blueprint for creating projects with predefined structure."""

    meta = {
        "collection": "project_blueprints",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            {"fields": ["organization_id", "category"]},
            "organization_id",
            "category",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    description = StringField()
    category = StringField()
    version = StringField(default="1.0")
    schema = DictField()  # Blueprint schema
    parameters = DictField()  # Configurable parameters
    created_by = ReferenceField("User", reverse_delete_rule=3)
    is_public = BooleanField(default=False)
    is_system = BooleanField(default=False)
    meta_data = DictField()


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
    form = ReferenceField("Form", reverse_delete_rule=2)
    project = ReferenceField("Project", reverse_delete_rule=2)
    major = IntField(default=1, min_value=0)
    minor = IntField(default=0, min_value=0)
    patch = IntField(default=0, min_value=0)

    @property
    def version_string(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
class CustomFieldTemplate(BaseDocument, SoftDeleteMixin):
    """Custom field templates for forms."""

    meta = {
        "collection": "custom_field_templates",
        "indexes": ["organization_id", "name"],
        "index_background": True,
    }

    organization_id = StringField()
    name = StringField()
    field_type = StringField()
    config = DictField()

class SnapshotStore(BaseDocument, SoftDeleteMixin):
    """Stores form snapshots for versioning."""

    meta = {
        "collection": "snapshot_stores",
        "indexes": ["form_id", "created_at"],
        "index_background": True,
    }

    form_id = ReferenceField("Form")
    snapshot_data = DictField()
    created_at = DateTimeField()
    meta_data = DictField()
