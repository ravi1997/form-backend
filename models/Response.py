from mongoengine import (
    StringField,
    ListField,
    ReferenceField,
    DictField,
    DateTimeField,
    BooleanField,
    IntField,
    BinaryField,
)
from datetime import datetime, timezone
from models.base import BaseDocument, SoftDeleteMixin


class FormResponse(BaseDocument, SoftDeleteMixin):
    """
    Primary data store for all form submissions.
    This serves as the source collection for database views.
    """

    meta = {
        "collection": "form_responses",
        "indexes": [
            "form",
            "project",
            "submitted_by",
            "-submitted_at",
            "organization_id",
            "is_deleted",
            # Multi-tenant compound indexes
            ("organization_id", "form", "-submitted_at"),
            ("organization_id", "project", "-submitted_at"),
            ("organization_id", "form", "is_deleted", "-submitted_at"), # Optimized for list views
            ("form", "status", "is_deleted"),
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True)

    # Context References
    project = ReferenceField("Project")
    form = ReferenceField("Form", required=True)
    form_version = ReferenceField("FormVersion")
    version = StringField()

    # Payload - The source for dynamic views
    # Keys should match question variable_names
    data = DictField(required=True)
    encrypted_data = DictField(default=dict) # Stores encrypted sensitive fields

    # Metadata
    submitted_by = StringField(required=True)
    submitted_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    ip_address = StringField()
    user_agent = StringField()

    # Status tracking for pipeline processing
    status = StringField(
        choices=(
            "submitted",
            "processed",
            "error",
            "archived",
            "pending",
            "approved",
            "rejected",
        ),
        default="submitted",
    )
    review_status = StringField(
        choices=("pending", "approved", "rejected"), default="pending"
    )

    meta_data = DictField()
    tags = ListField(StringField())

    # Additional fields used in routes
    is_draft = BooleanField(default=False)
    ai_results = DictField(default=dict)
    status_log = ListField(DictField())

    # Management fields
    updated_by = StringField()
    # is_deleted and deleted_at are inherited from SoftDeleteMixin
    deleted_by = StringField()

    def save(self, *args, **kwargs):
        """
        Custom save to handle Field-Level Encryption (FLE).
        If a field is marked as sensitive in the Form definition, it is moved to encrypted_data.
        """
        from utils.encryption import encrypt_value
        from models.Form import FormVersion
        
        # 1. Identify sensitive fields from the version snapshot
        sensitive_fields = set()
        
        # We prefer using the linked form_version which should be a FormVersion instance
        version_doc = None
        if self.form_version:
            # If it's a reference, MongoEngine might have it already or we fetch it
            if isinstance(self.form_version, FormVersion):
                version_doc = self.form_version
            else:
                version_doc = FormVersion.objects(id=self.form_version).first()
        
        if not version_doc and self.form:
            # Fallback to active version
            active_id = getattr(self.form, "active_version_id", None)
            if active_id:
                version_doc = FormVersion.objects(form=self.form.id, version=active_id).first()

        if version_doc:
            if version_doc.snapshot:
                # Optimized: Use snapshot tree
                def extract_sensitive(sections):
                    for sec in sections:
                        for q in sec.get("questions", []):
                            if q.get("is_sensitive"):
                                var_name = q.get("variable_name")
                                if var_name: sensitive_fields.add(var_name)
                        if sec.get("sections"):
                            extract_sensitive(sec["sections"])
                extract_sensitive(version_doc.snapshot.get("sections", []))
            else:
                # Legacy fallback
                for section in version_doc.sections:
                    for question in section.questions:
                        if question.is_sensitive:
                            sensitive_fields.add(question.variable_name)

        # 2. Process data payload
        for field in list(self.data.keys()):
            if field in sensitive_fields:
                val = self.data.pop(field)
                if val:
                    self.encrypted_data[field] = encrypt_value(str(val))

        return super().save(*args, **kwargs)

    def get_decrypted_data(self):
        """Returns the full data payload with sensitive fields decrypted."""
        from utils.encryption import decrypt_value
        full_data = self.data.copy()
        for field, enc_val in self.encrypted_data.items():
            full_data[field] = decrypt_value(enc_val)
        return full_data


class ResponseHistory(BaseDocument):
    meta = {
        "collection": "response_history",
        "indexes": ["response_id", "form_id", "-changed_at"],
    }
    response_id = StringField(required=True)
    form_id = StringField(required=True)
    data_before = DictField()
    data_after = DictField()
    changed_by = StringField(required=True)
    changed_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    change_type = StringField(default="update")  # 'create', 'update', 'delete'
    version = StringField()


class SavedSearch(BaseDocument):
    meta = {
        "collection": "saved_searches",
        "indexes": ["form", "user_id"],
    }
    name = StringField(required=True)
    form = ReferenceField("Form", required=True)
    user_id = StringField(required=True)
    query_json = DictField(required=True)
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))


class ResponseComment(BaseDocument):
    meta = {
        "collection": "response_comments",
        "indexes": ["response", "-created_at"],
    }
    response = ReferenceField("FormResponse", required=True)
    user = StringField(required=True)
    text = StringField(required=True)
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))


class SummarySnapshot(BaseDocument):
    meta = {
        "collection": "summary_snapshots",
        "indexes": ["form_id", "-timestamp"],
    }
    form_id = StringField(required=True)
    timestamp = DateTimeField(default=lambda: datetime.now(timezone.utc))
    period_start = DateTimeField(required=True)
    period_end = DateTimeField(required=True)
    period_label = StringField()
    response_count = IntField(default=0)
    strategy_used = StringField()
    summary_data = DictField()  # The actual summary content
    created_by = StringField()
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))


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

class BulkExport(BaseDocument):
    """Tracks status and stores results of background export jobs."""
    meta = {
        "collection": "bulk_exports",
        "indexes": ["organization_id", "status"],
        "index_background": True,
    }
    form_ids = ListField(StringField())
    status = StringField(choices=("pending", "processing", "completed", "failed"), default="pending")
    file_binary = BinaryField()
    filename = StringField()
    error_message = StringField()
    created_by = StringField()
    completed_at = DateTimeField()
