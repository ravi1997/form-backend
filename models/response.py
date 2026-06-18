"""
models/response.py
Form response and submission models.
"""

from mongoengine import (
    StringField, ListField, EmbeddedDocumentField, ReferenceField, DictField,
    BooleanField, DateTimeField, IntField, EmbeddedDocument, ValidationError
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument

# Import choice constants
from models.base import (
    RESPONSE_STATUS_CHOICES, REVIEW_STATUS_CHOICES
)


class Answer(BaseEmbeddedDocument):
    """Individual answer to a question."""

    question_id = StringField(required=True)
    value = StringField()
    display_value = StringField()
    file_ids = ListField(StringField())  # References to uploaded files
    answered_at = DateTimeField()
    iteration_index = IntField(default=0)
    meta_data = DictField()


class ResponseGroup(BaseEmbeddedDocument):
    """Repeated section/group in a response."""

    section_id = StringField(required=True)
    iteration = IntField(required=True)
    answers = DictField()  # question_id -> Answer
    meta_data = DictField()


class FormResponse(BaseDocument, SoftDeleteMixin):
    """Complete form submission with all answers."""

    meta = {
        "collection": "form_responses",
        "indexes": [
            {"fields": ["organization_id", "form_id", "respondent_id"]},
            {"fields": ["organization_id", "form_id", "submission_number"]},
            "organization_id",
            "form_id",
            "respondent_id",
            "status",
            "completed_at",
            "created_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    form_id = ReferenceField("Form", required=True, reverse_delete_rule=2)
    form_version_id = StringField()
    respondent_id = ReferenceField("User", reverse_delete_rule=3)
    respondent_email = StringField()
    session_id = StringField()
    status = StringField(choices=RESPONSE_STATUS_CHOICES, default="submitted")
    review_status = StringField(choices=REVIEW_STATUS_CHOICES, default="pending")
    
    # Response data
    answers = DictField()  # question_id -> Answer
    repeat_groups = ListField(EmbeddedDocumentField(ResponseGroup))
    
    # Metadata
    submission_number = IntField()
    ip_address = StringField()
    user_agent = StringField()
    device_type = StringField()
    platform = StringField()
    started_at = DateTimeField()
    completed_at = DateTimeField()
    time_taken_seconds = IntField()
    offline_submitted = BooleanField(default=False)
    is_legacy = BooleanField(default=False)  # For old form versions
    
    # Approval workflow
    approved_by = ReferenceField("User", reverse_delete_rule=3)
    approved_at = DateTimeField()
    rejected_by = ReferenceField("User", reverse_delete_rule=3)
    rejected_at = DateTimeField()
    rejection_reason = StringField()
    
    # File uploads
    file_uploads = ListField(StringField())  # References to file uploads
    
    meta_data = DictField()

    def clean(self):
        # Ensure either respondent_id or respondent_email is provided
        if not self.respondent_id and not self.respondent_email:
            raise ValidationError("Either respondent_id or respondent_email must be provided.")


class ResponseHistory(BaseDocument):
    """Audit trail for response changes."""

    meta = {
        "collection": "response_history",
        "indexes": [
            {"fields": ["organization_id", "response_id"]},
            "organization_id",
            "response_id",
            "changed_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    response_id = ReferenceField("FormResponse", required=True, reverse_delete_rule=2)
    changed_by = ReferenceField("User", reverse_delete_rule=3)
    changed_at = DateTimeField()
    change_type = StringField(choices=("created", "updated", "deleted", "approved", "rejected"))
    before_data = DictField()
    after_data = DictField()
    change_reason = StringField()
    meta_data = DictField()


class ResponseDraft(BaseDocument, SoftDeleteMixin):
    """Draft responses saved before submission."""

    meta = {
        "collection": "response_drafts",
        "indexes": [
            {"fields": ["organization_id", "form_id", "respondent_id"], "unique": True},
            {"fields": ["organization_id", "session_id"]},
            "organization_id",
            "form_id",
            "respondent_id",
            "expires_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    form_id = ReferenceField("Form", required=True, reverse_delete_rule=2)
    form_version_id = StringField()
    respondent_id = ReferenceField("User", reverse_delete_rule=3)
    session_id = StringField()
    partial_answers = DictField()  # question_id -> Answer
    repeat_groups = ListField(EmbeddedDocumentField(ResponseGroup))
    last_saved_at = DateTimeField()
    expires_at = DateTimeField()
    meta_data = DictField()


class SavedSearch(BaseDocument, SoftDeleteMixin):
    """Saved search configurations for filtering responses."""

    meta = {
        "collection": "saved_searches",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            "organization_id",
            "created_by",
            "is_public",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    description = StringField()
    form_id = ReferenceField("Form", reverse_delete_rule=3)
    search_criteria = DictField()  # Search filter configuration
    sort_criteria = DictField()  # Sort configuration
    column_selection = ListField(StringField())  # Selected columns for export
    created_by = ReferenceField("User", reverse_delete_rule=3)
    is_public = BooleanField(default=False)
    is_default = BooleanField(default=False)
    usage_count = IntField(default=0)
    meta_data = DictField()


class DynamicViewDefinition(BaseDocument, SoftDeleteMixin):
    """
    Stores the configuration for MongoDB Views.
    A backend service can use these definitions to run:
    db.createView(view_name, "form_responses", pipeline)
    """

    meta = {
        "collection": "view_definitions",
        "indexes": ["view_name", "form", "tags", "organization_id"],
        "index_background": True,
    }

    organization_id = StringField(required=True)
    view_name = StringField(required=True, unique=True)
    description = StringField()

    # The source form/project this view is based on
    form = ReferenceField("Form")
    project = ReferenceField("Project")

    # The Aggregation Pipeline that defines the view
    # e.g. [{ "$match": { "form": "..." } }, { "$project": { "data.name": 1 } }]
    pipeline = ListField(DictField(), required=True)

    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    tags = ListField(StringField())
class SummarySnapshot(BaseDocument, SoftDeleteMixin):
    """AI-generated summary snapshots for forms."""

    meta = {
        "collection": "summary_snapshots",
        "indexes": [
            {"fields": ["organization_id", "form_id", "period_start"]},
            "organization_id",
            "form_id",
            "created_by",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    form_id = ReferenceField("Form", reverse_delete_rule=3)
    period_start = DateTimeField()
    period_end = DateTimeField()
    period_label = StringField()
    response_count = IntField(default=0)
    strategy_used = StringField()
    summary_data = StringField()
    created_by = ReferenceField("User", reverse_delete_rule=3)
    timestamp = DateTimeField()
    meta_data = DictField()

class AnomalyThreshold(BaseDocument, SoftDeleteMixin):
    """Anomaly detection thresholds for form analytics."""

    meta = {
        "collection": "anomaly_thresholds",
        "indexes": [
            {"fields": ["organization_id", "form_id"]},
            "organization_id",
            "form_id",
            "question_id",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    form_id = ReferenceField("Form", reverse_delete_rule=3)
    question_id = StringField()
    threshold_type = StringField(choices=("statistical", "custom"))
    threshold_value = StringField()
    algorithm = StringField(default="zscore")
    created_by = ReferenceField("User", reverse_delete_rule=3)
    created_at = DateTimeField()
    meta_data = DictField()

class BulkExport(BaseDocument, SoftDeleteMixin):
    """Bulk export job tracking."""

    meta = {
        "collection": "bulk_exports",
        "indexes": ["organization_id", "status", "created_at"],
        "index_background": True,
    }

    organization_id = StringField(required=True)
    form_ids = ListField(StringField())
    created_by = ReferenceField("User", reverse_delete_rule=3)
    status = StringField(choices=("pending", "processing", "completed", "failed"), default="pending")
    file_path = StringField()
    error_message = StringField()
    created_at = DateTimeField()
    completed_at = DateTimeField()
    meta_data = DictField()
