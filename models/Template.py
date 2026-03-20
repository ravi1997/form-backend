from mongoengine import (
    StringField,
    ListField,
    EmbeddedDocumentField,
    DictField,
    BooleanField,
    ReferenceField,
    IntField,
    DateTimeField,
)
from datetime import datetime, timezone
from models.base import BaseDocument

# Import structural elements to be used as blueprint pieces
from models.Form import Section, ResponseTemplate, Question


class CustomFieldTemplate(BaseDocument):
    meta = {
        "collection": "custom_field_templates",
        "indexes": ["user_id", "category", "template_type"],
        "index_background": True,
    }
    user_id = StringField(required=True)
    name = StringField(required=True)
    category = StringField()
    template_type = StringField(default="question")  # 'question', 'form', 'section'
    data = DictField()
    question_data = EmbeddedDocumentField(Question)
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))


class FormBlueprint(BaseDocument):
    """
    A reusable template for Forms.
    Stores the entire hierarchical structure (Sections -> Questions -> Options).
    Used to quickly bootstrap new form structures.
    """

    meta = {
        "collection": "form_blueprints",
        "indexes": ["category", "tags", "is_official"],
        "index_background": True,
    }

    name = StringField(required=True, trim=True)
    description = StringField()
    category = StringField()
    tags = ListField(StringField())

    # Structure Content
    # These contain the exact sections and questions defined in the blueprint
    sections = ListField(ReferenceField(Section))
    response_templates = ListField(EmbeddedDocumentField(ResponseTemplate))

    # Template Store Metadata
    icon = StringField()  # Emoji, Icon name, or URL
    estimated_completion_time = IntField()  # Helpful UI hint (minutes)
    industry = StringField()
    usage_count = IntField(default=0)  # Tracks popularity

    is_official = BooleanField(default=False)  # Distinguish system vs user templates
    meta_data = DictField()


class ProjectBlueprint(BaseDocument):
    """
    A template for entire Project structures.
    Allows for one-click creation of complex multi-form environments.
    """

    meta = {
        "collection": "project_blueprints",
        "indexes": ["tags"],
        "index_background": True,
    }

    name = StringField(required=True, trim=True)
    description = StringField()
    tags = ListField(StringField())

    # Composition: References existing Form Blueprints
    form_blueprints = ListField(ReferenceField(FormBlueprint))

    # Deployment Logic
    # Defines how the project tree (sub-projects) should be instantiated
    hierarchy_definition = DictField()

    is_template = BooleanField(default=True)
    meta_data = DictField()
