from datetime import datetime, timezone

from mongoengine import (
    DictField,
    DateTimeField,
    IntField,
    StringField,
)

from models.base import BaseDocument, SoftDeleteMixin


class AIModelRegistry(BaseDocument, SoftDeleteMixin):
    """
    Registry of AI model promotions and rollback state for tenant-scoped deployments.
    Tracks active versions, evaluation scores, and promotion lifecycle transitions.
    """

    meta = {
        "collection": "ai_model_registry",
        "indexes": [
            ("organization_id", "model_name"),
            ("organization_id", "status"),
            ("organization_id", "active_version"),
            {"fields": ["organization_id", "model_name", "version"], "unique": True},
        ],
        "index_background": True,
    }

    STATUS_DRAFT = "draft"
    STATUS_PENDING_REVIEW = "pending_review"
    STATUS_PROMOTED = "promoted"
    STATUS_ACTIVE = "active"
    STATUS_ROLLED_BACK = "rolled_back"
    STATUS_SUPERSEDED = "superseded"
    STATUS_HOLD = "hold"

    VALID_STATUSES = {
        STATUS_DRAFT,
        STATUS_PENDING_REVIEW,
        STATUS_PROMOTED,
        STATUS_ACTIVE,
        STATUS_ROLLED_BACK,
        STATUS_SUPERSEDED,
        STATUS_HOLD,
    }

    model_name = StringField(required=True)
    version = StringField(required=True)
    status = StringField(required=True, choices=tuple(sorted(VALID_STATUSES)), default=STATUS_DRAFT)
    active_version = StringField(required=False, default="")
    previous_version = StringField(required=False, default="")
    rollout_state = StringField(required=False, default="inactive")
    evaluation_score = IntField(required=False, default=0)
    evaluation_details = DictField(default=dict)
    rollback_reason = StringField(required=False, default="")
    rollback_target_version = StringField(required=False, default="")
    promoted_at = DateTimeField()
    activated_at = DateTimeField()
    rolled_back_at = DateTimeField()
    held_at = DateTimeField()

    @staticmethod
    def now():
        return datetime.now(timezone.utc)

    def mark_promoted(self, active_version: str, previous_version: str = "") -> None:
        self.status = self.STATUS_PROMOTED
        self.active_version = active_version
        self.previous_version = previous_version
        self.rollout_state = "promoted"
        self.promoted_at = self.now()

    def mark_active(self) -> None:
        self.status = self.STATUS_ACTIVE
        self.rollout_state = "active"
        self.activated_at = self.now()

    def mark_hold(self, reason: str = "") -> None:
        self.status = self.STATUS_HOLD
        self.rollout_state = "hold"
        self.rollback_reason = reason
        self.held_at = self.now()

    def mark_rolled_back(self, target_version: str, reason: str = "") -> None:
        self.status = self.STATUS_ROLLED_BACK
        self.rollout_state = "rolled_back"
        self.rollback_target_version = target_version
        self.rollback_reason = reason
        self.rolled_back_at = self.now()
