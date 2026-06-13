from mongoengine import (
    StringField,
    ListField,
    ReferenceField,
    DictField,
    DateTimeField,
    BooleanField,
    IntField,
    BinaryField,
    UUIDField,
)
from datetime import datetime, timezone
from uuid import UUID
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
            ("organization_id", "form", "is_deleted", "-submitted_at"),
            ("form", "status", "is_deleted"),
            # Idempotency: prevent duplicate submissions on retry
            {
                "fields": ["organization_id", "idempotency_key"],
                "unique": True,
                "sparse": True,
                "name": "org_idempotency_unique",
            },
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True)

    # Context References
    project = StringField()
    form = UUIDField(required=True, binary=False)
    form_version = StringField()
    version = StringField()
    commit_id = UUIDField(binary=False)
    detached_data = DictField(default=dict)

    # Payload - The source for dynamic views
    # Keys should match question variable_names
    data = DictField(required=True)
    encrypted_data = DictField(default=dict)  # Stores encrypted sensitive fields

    # Idempotency key — client-supplied UUID to prevent duplicate submissions on retry
    # Enforced unique per (organization_id, idempotency_key) via sparse index
    idempotency_key = StringField(sparse=True)

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
        from models.Form import Form, FormVersion

        if isinstance(self.commit_id, UUID):
            self.commit_id = str(self.commit_id)

        # 1. Identify sensitive fields from the version snapshot
        sensitive_fields = set()

        # We prefer using the linked form_version which should be a FormVersion instance
        version_doc = None
        raw_form_version = self._data.get("form_version")
        if raw_form_version:
            # If it's a reference, MongoEngine might have it already or we fetch it
            if isinstance(raw_form_version, FormVersion):
                version_doc = raw_form_version
            else:
                version_doc = FormVersion.objects(
                    id=getattr(raw_form_version, "id", raw_form_version)
                ).first()

        if not version_doc:
            # Avoid dereferencing self.form directly; ReferenceField dereference can fail
            # when raw refs/DBRefs are present in request-time save paths.
            raw_form_ref = self._data.get("form")
            form_id = getattr(raw_form_ref, "id", raw_form_ref)
            if form_id:
                form_doc = (
                    Form.objects(
                        id=form_id,
                        organization_id=self.organization_id,
                        is_deleted=False,
                    )
                    .only("active_version")
                    .first()
                )
                active_id = (
                    getattr(form_doc, "active_version_id", None) if form_doc else None
                )
                if active_id:
                    version_doc = FormVersion.objects(
                        form=form_id,
                        version=active_id,
                        organization_id=self.organization_id,
                    ).first()

        if version_doc:
            snapshot = version_doc.resolved_snapshot or {}

            def extract_sensitive(sections):
                for sec in sections:
                    for q in sec.get("questions", []):
                        if q.get("is_sensitive"):
                            var_name = q.get("variable_name")
                            if var_name:
                                sensitive_fields.add(var_name)
                    if sec.get("sections"):
                        extract_sensitive(sec["sections"])

            extract_sensitive(snapshot.get("sections", []))

        # 2. Process data payload
        for field in list(self.data.keys()):
            if field in sensitive_fields:
                val = self.data.get(field)
                if val:
                    self.encrypted_data[field] = encrypt_value(str(val))
                    # Keep key shape for downstream logic while preventing plaintext at rest.
                    self.data[field] = None

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


class SearchHistory(BaseDocument):
    meta = {
        "collection": "search_history",
        "indexes": ["form_id", "user_id", "-created_at"],
    }

    form_id = StringField(required=True)
    user_id = StringField(required=True)
    query = StringField(required=True)
    results_count = IntField(default=0)
    parsed_intent = DictField(default=dict)
    search_type = StringField(default="nlp")
    cached = BooleanField(default=False)
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
    status = StringField(
        choices=("pending", "processing", "completed", "failed"), default="pending"
    )
    file_binary = BinaryField()
    filename = StringField()
    error_message = StringField()
    created_by = StringField()
    completed_at = DateTimeField()
