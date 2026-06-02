"""
models/EvidenceLog.py
Model for storing compliance and evidence tracking logs.
Provides a tamper-evident/read-only registry of compliance and security actions.
"""

import hashlib
import json
from mongoengine import StringField, DictField, DateTimeField
from datetime import datetime, timezone
from .base import BaseDocument, SoftDeleteMixin

class EvidenceLog(BaseDocument, SoftDeleteMixin):
    """
    Evidence Tracking Log for compliance-critical changes.
    Enforces a cryptographic record signature to verify integrity.
    """

    meta = {
        "collection": "evidence_logs",
        "indexes": [
            "organization_id",
            "event_type",
            "-timestamp",
            "record_hash",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True)
    event_type = StringField(required=True)  # e.g., 'retention_prune', 'legal_hold_created', 'legal_hold_released'
    actor_id = StringField(required=True)
    details = DictField(default=dict)
    timestamp = DateTimeField(default=lambda: datetime.now(timezone.utc))
    record_hash = StringField()

    def generate_hash(self) -> str:
        """Generates a SHA-256 hash of the evidence details and metadata for verification."""
        payload = {
            "organization_id": self.organization_id,
            "event_type": self.event_type,
            "actor_id": self.actor_id,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "details": self.details
        }
        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def save(self, *args, **kwargs):
        if not self.record_hash:
            self.record_hash = self.generate_hash()
        return super().save(*args, **kwargs)
