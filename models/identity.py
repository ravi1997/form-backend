"""
models/identity.py
Identity and access management models: User, Organization, Group, and Membership.
"""

import bcrypt
import logging
from enum import Enum
from datetime import datetime, timedelta, timezone
from mongoengine import (
    StringField, EmailField, DateTimeField, BooleanField, ListField, IntField,
    Q, ReferenceField, DictField, ValidationError
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument

# Import choice constants
from models.base import (
    USER_TYPE_CHOICES, ROLE_CHOICES, STATUS_CHOICES
)


# Logger Setup
logger = logging.getLogger("auth")


class User(BaseDocument, SoftDeleteMixin):
    """
    Standardized User model using BaseDocument for UUIDs and Timestamps.
    """

    meta = {
        "collection": "users",
        "indexes": [
            {"fields": ["username"], "unique": True, "sparse": True},
            {"fields": ["email"], "unique": True},
            {"fields": ["employee_id"], "unique": True, "sparse": True},
            {"fields": ["mobile"], "unique": True, "sparse": True},
            "organization_id",
        ],
        "index_background": True,
    }

    username = StringField(max_length=50, trim=True)
    email = EmailField(trim=True)
    employee_id = StringField(max_length=30, trim=True)
    mobile = StringField(max_length=15, trim=True)
    department = StringField(trim=True)
    organization_id = StringField(trim=True)  # Multi-tenant support
    sso_provider = StringField(trim=True)
    sso_id = StringField(trim=True)

    user_type = StringField(required=True, choices=USER_TYPE_CHOICES, default="general")
    password_hash = StringField(max_length=255)
    password_expiration = DateTimeField()
    password_history = ListField(StringField(), default=list)

    is_active = BooleanField(default=True)
    is_admin = BooleanField(default=False)
    is_email_verified = BooleanField(default=False)

    roles = ListField(StringField(choices=ROLE_CHOICES), default=list)

    # Security State
    failed_login_attempts = IntField(default=0)
    otp_resend_count = IntField(default=0)
    lock_until = DateTimeField()
    last_login = DateTimeField()
    last_token_revocation_at = DateTimeField()

    # Redundant OTP fields removed as we migrated to secure Redis storage.

    def is_locked(self) -> bool:
        if not self.lock_until:
            return False
        lock_until = self.lock_until
        if lock_until.tzinfo is None:
            lock_until = lock_until.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < lock_until

    def lock_account(self, duration_hours=24):
        self.lock_until = datetime.now(timezone.utc) + timedelta(hours=duration_hours)
        logger.warning(f"User {self.id} locked until {self.lock_until}")
        self.save()

    def unlock_account(self):
        self.lock_until = None
        self.failed_login_attempts = 0
        self.otp_resend_count = 0
        logger.info(f"User {self.id} manually unlocked")
        self.save()

    def reset_failed_logins(self):
        self.failed_login_attempts = 0
        self.lock_until = None
        self.save()

    def is_admin_check(self) -> bool:
        return self.is_admin or "admin" in self.roles or "superadmin" in self.roles

    def is_superadmin_check(self) -> bool:
        return "superadmin" in self.roles

    def increment_failed_logins(self, max_attempts=5, lock_hours=24):
        if self.is_locked():
            return
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= max_attempts:
            self.lock_account(duration_hours=lock_hours)
        else:
            self.save()

    def set_password(self, raw_password: str, expiry_days=90):
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(raw_password.encode(), salt).decode()
        self.password_expiration = datetime.now(timezone.utc) + timedelta(
            days=expiry_days
        )
        self.password_history = getattr(self, "password_history", []) or []
        self.password_history.append(self.password_hash)
        self.password_history = self.password_history[-5:]

    def check_password(self, raw_password: str) -> bool:
        try:
            return bcrypt.checkpw(raw_password.encode(), self.password_hash.encode())
        except Exception:
            return False

    def is_password_expired(self) -> bool:
        if not self.password_expiration:
            return False
        pw_exp = self.password_expiration
        if pw_exp.tzinfo is None:
            pw_exp = pw_exp.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > pw_exp

    @staticmethod
    def authenticate(identifier: str, password: str) -> "User | None":
        user = User.objects(
            Q(is_active=True)
            & Q(is_deleted=False)
            & (Q(username=identifier) | Q(email=identifier) | Q(employee_id=identifier))
        ).first()

        if not user or user.is_locked():
            return None

        # These defaults should ideally be fetched from SystemSettings in the service layer
        if not user.check_password(password):
            user.increment_failed_logins()
            return None

        if user.is_password_expired():
            return None

        user.last_login = datetime.now(timezone.utc)
        user.reset_failed_logins()
        user.save()
        return user

    def __str__(self):
        return f"<User(username='{self.username}', id='{self.id}')>"


class Organization(BaseDocument, SoftDeleteMixin):
    """
    Represents an Enterprise Organization (tenant).
    Contains basic identity, status (active/suspended), administrative mappings, and metadata.
    """

    meta = {
        "collection": "organizations",
        "indexes": [
            {"fields": ["organization_id"], "unique": True},
            {"fields": ["status"]},
            {"fields": ["parent_org_id"]},
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, unique=True)
    name = StringField(required=True)
    display_name = StringField(required=True)
    status = StringField(choices=["active", "suspended"], default="active")
    admin_user_id = StringField(required=False)  # Maps to User.id (as UUID string or user_id)
    contact_email = StringField(required=False)
    description = StringField(required=False)
    parent_org_id = StringField(required=False, default=None)
    org_type = StringField(choices=["organisation", "department", "team", "unit"], default="organisation")
    storage_quota_bytes = IntField(default=107374182400)  # 100 GB default
    storage_used_bytes = IntField(default=0)
    compliance_ids = ListField(StringField(), default=list)
    metadata = DictField(default=dict)

    @classmethod
    def get_or_create(cls, organization_id: str, name: str = None, display_name: str = None) -> "Organization":
        """Gets settings for the specified organization_id, or creates a default one if it doesn't exist."""
        doc = cls.objects(organization_id=organization_id).first()
        if doc:
            return doc

        import uuid
        name = name or organization_id
        display_name = display_name or name

        try:
            cls._get_collection().update_one(
                {"organization_id": organization_id},
                {"$setOnInsert": {
                    "_id": str(uuid.uuid4()),
                    "organization_id": organization_id,
                    "name": name,
                    "display_name": display_name,
                    "status": "active",
                    "admin_user_id": None,
                    "contact_email": None,
                    "description": None,
                    "parent_org_id": None,
                    "org_type": "organisation",
                    "storage_quota_bytes": 107374182400,
                    "storage_used_bytes": 0,
                    "compliance_ids": [],
                    "metadata": {},
                    "is_deleted": False,
                }},
                upsert=True,
            )
        except Exception:
            pass

        return cls.objects(organization_id=organization_id).first()


class Invitation(BaseDocument, SoftDeleteMixin):
    """
    User invitation for organization membership.
    """

    meta = {
        "collection": "invitations",
        "indexes": [
            {"fields": ["organization_id", "token"], "unique": True},
            {"fields": ["organization_id", "invited_email"]},
            {"fields": ["organization_id", "status"]},
            {"fields": ["expires_at"], "expireAfterSeconds": 0},
            "organization_id",
            "status",
            "expires_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    token = StringField(required=True, unique=True)
    invited_email = StringField(required=True)
    invited_by = ReferenceField("User", required=True, reverse_delete_rule=3)
    role = StringField(default="member")
    status = StringField(choices=("pending", "accepted", "expired", "revoked"), default="pending")
    expires_at = DateTimeField()
    accepted_at = DateTimeField()
    accepted_by = ReferenceField("User", reverse_delete_rule=3)
    created_at = DateTimeField()
    meta_data = DictField()


class Group(BaseDocument, SoftDeleteMixin):
    """
    Organization-scoped group used for access control and membership management.
    """

    meta = {
        "collection": "groups",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            {"fields": ["organization_id", "slug"], "unique": True, "sparse": True},
            "organization_id",
            "is_active",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    slug = StringField(trim=True)
    description = StringField()
    owner = ReferenceField("User", reverse_delete_rule=2)
    created_by = ReferenceField("User", reverse_delete_rule=3)
    members = ListField(ReferenceField("User"))
    is_active = BooleanField(default=True)
    created_from_invitation = ReferenceField("Invitation", reverse_delete_rule=3)
    last_used_at = DateTimeField()


class GroupMember(BaseDocument, SoftDeleteMixin):
    """
    Explicit membership edge between a user and a group.
    """

    meta = {
        "collection": "group_members",
        "indexes": [
            {"fields": ["group", "user"], "unique": True},
            "organization_id",
            "group",
            "user",
            "status",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    group = ReferenceField("Group", required=True, reverse_delete_rule=2)
    user = ReferenceField("User", required=True, reverse_delete_rule=2)
    role = StringField(default="member")
    status = StringField(
        choices=("pending", "active", "suspended", "removed"),
        default="active",
    )
    invited_by = ReferenceField("User", reverse_delete_rule=3)
    joined_at = DateTimeField()
    is_admin = BooleanField(default=False)


class OrgMembership(BaseDocument, SoftDeleteMixin):
    """
    Maps a user to an organization and tracks the user's membership lifecycle.
    """

    meta = {
        "collection": "org_memberships",
        "indexes": [
            {"fields": ["organization_id", "user"], "unique": True},
            "organization_id",
            "user",
            "status",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    user = ReferenceField("User", required=True, reverse_delete_rule=2)
    role = StringField(required=True, default="member")
    status = StringField(
        choices=("pending", "active", "suspended", "removed"),
        default="pending",
    )
    invited_by = ReferenceField("User", reverse_delete_rule=3)
    joined_at = DateTimeField()
    last_active_at = DateTimeField()
    is_primary = BooleanField(default=False)


class TenantSettings(BaseDocument, SoftDeleteMixin):
    """
    Stores tenant settings, configuration, and quotas for form limits, submission limits, etc.
    Usage metrics are updated periodically or in real-time.
    """

    meta = {
        "collection": "tenant_settings",
        "indexes": [
            {"fields": ["organization_id"], "unique": True},
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, unique=True)
    is_active = BooleanField(default=True)

    # ── Tenant Quotas ──
    max_forms = IntField(default=100)
    max_submissions = IntField(default=10000)
    storage_limit_mb = IntField(default=1024)

    # ── Compliance Settings ──
    retention_days = IntField(default=365)  # Auto-expire responses older than this

    # ── Current Resource Usage ──
    usage_forms_count = IntField(default=0)
    usage_submissions_count = IntField(default=0)
    usage_storage_bytes = IntField(default=0)

    @classmethod
    def get_or_create(cls, organization_id: str) -> "TenantSettings":
        """Gets settings for the specified organization_id, or creates a default one if it doesn't exist."""
        doc = cls.objects(organization_id=organization_id).first()
        if doc:
            return doc

        import uuid
        try:
            cls._get_collection().update_one(
                {"organization_id": organization_id},
                {"$setOnInsert": {
                    "_id": str(uuid.uuid4()),
                    "organization_id": organization_id,
                    "is_active": True,
                    "max_forms": 100,
                    "max_submissions": 10000,
                    "storage_limit_mb": 1024,
                    "retention_days": 365,
                    "usage_forms_count": 0,
                    "usage_submissions_count": 0,
                    "usage_storage_bytes": 0,
                    "is_deleted": False,
                }},
                upsert=True,
            )
        except ValidationError:
            pass

        return cls.objects(organization_id=organization_id).first()