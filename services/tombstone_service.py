from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from logger.unified_logger import app_logger, audit_logger
from models.Tombstone import Tombstone


class TombstoneService:
    """Encapsulates tombstone creation, retrieval, and retention cleanup."""

    def record_delete(
        self, organization_id: str, entity_type: str, entity_id: str
    ) -> Tombstone:
        tombstone = Tombstone(
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=str(entity_id),
        )
        tombstone.save()
        audit_logger.info(
            f"Recorded tombstone for {entity_type}:{entity_id} in org {organization_id}"
        )
        return tombstone

    def list_since(
        self,
        organization_id: str,
        since: Optional[datetime] = None,
        entity_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        query = Tombstone.objects(organization_id=organization_id)
        if since:
            query = query(deleted_at__gt=since)
        if entity_types:
            query = query(entity_type__in=entity_types)

        tombstones = query.order_by("deleted_at")
        return [
            {
                "entity_type": tombstone.entity_type,
                "entity_id": tombstone.entity_id,
                "deleted_at": tombstone.deleted_at.isoformat()
                if tombstone.deleted_at
                else None,
            }
            for tombstone in tombstones
        ]

    def prune_old_tombstones(self, retention_days: int = 30) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        deleted_count = Tombstone.objects(deleted_at__lt=cutoff).delete()
        app_logger.info(
            f"Pruned {deleted_count} tombstones older than {retention_days} days"
        )
        return deleted_count
