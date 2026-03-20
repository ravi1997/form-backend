import bcrypt
import logging
from enum import Enum
from datetime import datetime, timedelta, timezone
from mongoengine import (
    StringField,
    EmailField,
    DateTimeField,
    BooleanField,
    ListField,
    IntField,
    Q,
)
from models.base import BaseDocument, SoftDeleteMixin
from models.enumerations import USER_TYPE_CHOICES, ROLE_CHOICES


class Role(str, Enum):
    """
    Enum of all supported user roles.
    Using str mixin allows direct comparison with string values from JWT claims.
    """

    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    USER = "user"
    CREATOR = "creator"
    EDITOR = "editor"
    PUBLISHER = "publisher"
    DEO = "deo"
    MANAGER = "manager"
    GENERAL = "general"


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
            {"fields": ["email"], "unique": True, "sparse": True},
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

    user_type = StringField(required=True, choices=USER_TYPE_CHOICES)
    password_hash = StringField(max_length=255)
    password_expiration = DateTimeField()

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

    def increment_failed_logins(self, max_attempts=5, lock_hours=24):
        if self.is_locked():
            return
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= max_attempts:
            self.lock_account(duration_hours=lock_hours)
        else:
            self.save()

    def reset_failed_logins(self):
        self.failed_login_attempts = 0

    def reset_failed_logins(self):
        self.failed_login_attempts = 0

    def set_password(self, raw_password: str, expiry_days=90):
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(raw_password.encode(), salt).decode()
        self.password_expiration = datetime.now(timezone.utc) + timedelta(
            days=expiry_days
        )

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
            Q(is_active=True) & 
            Q(is_deleted=False) & (
                Q(username=identifier) | 
                Q(email=identifier) | 
                Q(employee_id=identifier)
            )
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
