"""
models/base.py
Base classes, mixins, and enumerations for all models.
"""

from mongoengine import (
    Document,
    EmbeddedDocument,
    DateTimeField,
    UUIDField,
    BooleanField,
    StringField,
    QuerySet,
)
import uuid
from datetime import datetime, timezone
from flask import has_request_context
from flask_jwt_extended import current_user
from enum import Enum


# --- ENUMS ---

STATUS_CHOICES = ("draft", "published", "archived")

# --- User & Auth Choices ---
USER_TYPE_CHOICES = ("employee", "general")

ROLE_CHOICES = (
    "superadmin",
    "admin",
    "user",
    "creator",
    "approver",
    "editor",
    "publisher",
    "deo",
    "manager",
    "general",
)


class Role(Enum):
    """User role enumeration."""
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    USER = "user"
    CREATOR = "creator"
    APPROVER = "approver"
    EDITOR = "editor"
    PUBLISHER = "publisher"
    DEO = "deo"
    MANAGER = "manager"
    GENERAL = "general"

UI_TYPE_CHOICES = (
    "flex", "grid-cols-2", "tabbed", "custom", "grid-cols-3", "full-width",
    "card", "list", "sidebar", "split", "overlay", "dashboard", "centered",
    "stacked", "masonry", "fixed", "standard", "grid", "accordion", "wizard",
    "threeColumns", "fullWidth",
)

FIELD_TYPE_CHOICES = (
    "input", "textarea", "number", "email", "mobile", "url", "password", "tel",
    "calculate", "note", "select", "dropdown", "radio", "checkbox", "multi_select",
    "checkboxes", "matrix_choice", "boolean", "rating", "date", "time", "datetime",
    "datetime-local", "month", "week", "file_upload", "multi-file_upload",
    "file_picker", "file_list", "image", "video_upload", "audio_upload", "signature",
    "signature_pad", "image_gallery", "map_location", "address", "address_lookup",
    "calculated", "api_search", "otp", "short_text", "paragraph", "rich_text",
    "textarea_editor", "markdown_editor", "color_picker", "slider", "range",
    "date_range", "time_range", "stepper", "country_select", "state_select",
    "city_select", "social_media_handle", "website_url", "phone_number", "captcha",
    "unit_select", "price", "age", "toggle", "hidden", "custom_field",
    "multi_checkbox", "email_list", "qr_code_scan", "search", "file",
)

FIELD_API_CALL_CHOICES = ("uhid", "employee_id", "form", "otp", "custom")

# --- Condition Choices ---
CONDITION_TYPE_CHOICES = ("simple", "group")
LOGICAL_OPERATOR_CHOICES = ("AND", "OR", "NOT", "NOR", "NAND")
CONDITION_SOURCE_TYPE_CHOICES = (
    "field", "hidden_field", "url_param", "user_info", "calculated_value",
)
CONDITION_OPERATOR_CHOICES = (
    "equals", "not_equals", "greater_than", "less_than", "greater_than_equals",
    "less_than_equals", "contains", "not_contains", "starts_with", "ends_with",
    "is_empty", "is_not_empty", "in_list", "not_in_list", "matches_regex",
    "between", "is_checked",
)
COMPARISON_TYPE_CHOICES = ("constant", "field", "url_param", "user_info", "calculation")

# --- Response Choices ---
RESPONSE_STATUS_CHOICES = ("submitted", "processed", "error", "archived")
REVIEW_STATUS_CHOICES = ("pending", "approved", "rejected")

# --- Access Control Choices ---
ACCESS_LEVEL_CHOICES = ("private", "group", "organization", "public")
RESOURCE_TYPE_CHOICES = ("form", "project", "submission", "view")
PERMISSION_CHOICES = (
    "view", "edit", "delete", "publish", "export_data", "manage_access",
    "approve_submissions", "approve_hooks",
)

# --- Approval Workflow Choices ---
APPROVAL_TYPE_CHOICES = ("sequential", "parallel", "maker-checker", "any_one")
WORKFLOW_STATUS_CHOICES = ("pending", "in_review", "approved", "rejected", "reverted")

# --- Trigger Choices ---
TRIGGER_EVENT_CHOICES = (
    "on_load", "on_submit", "on_change", "on_status_change", "on_validate",
    "on_approval_step", "on_creation",
)
TRIGGER_ACTION_CHOICES = (
    "webhook", "email", "sms", "notification", "update_field", "execute_script",
    "hide_show", "enable_disable", "validation_error", "calculation", "api_call",
    "form_data", "external_hook", "predefined_url",
)


# --- BASE CLASSES ---

class TenantIsolatedSoftDeleteQuerySet(QuerySet):
    """
    Automatically filters out deleted documents AND strictly enforces organization_id boundaries based on the active JWT user context.
    """

    def __call__(self, q_obj=None, **query):
        model = getattr(self, "_document", None)
        if model is None:
            return super().__call__(q_obj, **query)

        # 1. Enforce Soft Delete
        if "is_deleted" not in query and "is_deleted" in model._fields:
            query["is_deleted"] = False

        # 2. Enforce Tenant Isolation Boundary
        if has_request_context() and current_user:
            if "organization_id" in model._fields:
                # Superadmins bypass automatic isolation for cross-tenant operations
                user_roles = tuple(getattr(current_user, "roles", []) or ())
                if "superadmin" not in user_roles:
                    # STRICT: Snapshot the org once to avoid mid-call context drift.
                    user_org = getattr(current_user, "organization_id", None)
                    query["organization_id"] = user_org

        return super().__call__(q_obj, **query)

    def deleted(self):
        """Returns only deleted documents."""
        return self(is_deleted=True)

    def all_with_deleted(self):
        """Returns all documents including deleted ones."""
        return super().__call__()


class TimestampMixin:
    """
    Standardizes created_at and updated_at timestamps across all models.
    """

    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = DateTimeField(default=lambda: datetime.now(timezone.utc))

    def update_timestamp(self):
        """Refreshes the updated_at timestamp to the current UTC time."""
        self.updated_at = datetime.now(timezone.utc)


class SoftDeleteMixin:
    """
    Adds is_deleted and deleted_at fields to support non-permanent deletion.
    """

    is_deleted = BooleanField(default=False)
    deleted_at = DateTimeField()

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc)
        self.save()

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save()


class BaseEmbeddedDocument(EmbeddedDocument, TimestampMixin):
    """
    Abstract base for all embedded documents, providing automatic ID and timestamping.
    """

    meta = {"abstract": True}
    id = StringField(default=lambda: str(uuid.uuid4()))


class BaseDocument(Document, TimestampMixin):
    """
    Abstract base for all top-level documents, providing automatic ID and timestamping.
    """

    meta = {"abstract": True, "queryset_class": TenantIsolatedSoftDeleteQuerySet}
    id = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = StringField(
        required=False, help_text="Global tenant partition key. Do not modify manually."
    )

    def save(self, *args, **kwargs):
        self.update_timestamp()

        if has_request_context() and current_user:
            user_roles = tuple(getattr(current_user, "roles", []) or ())
            if "superadmin" not in user_roles:
                user_org = getattr(current_user, "organization_id", None)
                if user_org:
                    self.organization_id = user_org

        return super().save(*args, **kwargs)

    def to_dict(self):
        """Converts the document to a dictionary, stringifying the UUID ID."""
        data = self.to_mongo().to_dict()
        if "_id" in data:
            data["id"] = str(data.pop("_id"))

        # Stringify any native datetime objects
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()

        return data