from mongoengine import (
    Document,
    EmbeddedDocument,
    DateTimeField,
    UUIDField,
    BooleanField,
    StringField,
)
import uuid
from datetime import datetime, timezone
from mongoengine import QuerySet
from flask import has_request_context
from flask_jwt_extended import current_user

class TenantIsolatedSoftDeleteQuerySet(QuerySet):
    """
    Automatically filters out deleted documents AND strictly enforces organization_id boundaries based on the active JWT user context.
    """
    def __call__(self, q_obj=None, **query):
        # 1. Enforce Soft Delete
        if "is_deleted" not in query and "is_deleted" in self._model._fields:
            query["is_deleted"] = False
            
        # 2. Enforce Tenant Isolation Boundary
        if has_request_context() and current_user:
            if "organization_id" in self._model._fields and "organization_id" not in query:
                # Superadmins bypass automatic isolation for cross-tenant operations
                if "superadmin" not in getattr(current_user, "roles", []):
                    query["organization_id"] = getattr(current_user, "organization_id", None)
                    
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
    id = UUIDField(default=uuid.uuid4, binary=False)


class BaseDocument(Document, TimestampMixin):
    """
    Abstract base for all top-level documents, providing automatic ID and timestamping.
    """

    meta = {"abstract": True, "queryset_class": TenantIsolatedSoftDeleteQuerySet}
    id = UUIDField(primary_key=True, default=uuid.uuid4, binary=False)
    organization_id = StringField(required=False, help_text="Global tenant partition key. Do not modify manually.")

    def save(self, *args, **kwargs):
        self.update_timestamp()
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
