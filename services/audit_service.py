from models.AuditLog import AuditLog
from datetime import datetime, timezone
from schemas.base import InboundPayloadSchema
from schemas.response import FormResponseSchema # Reused generically here for DTO compliance

class AuditService:
    @staticmethod
    def append_event(tenant_id: str, actor_id: str, action: str, resource: str, metadata: dict = None):
        """
        [Phase 13: Compliance and Audit System]
        Enforces Append-Only immutability rules. Existing documents are
        never queried or updated by this service boundary.
        """
        log = AuditLog(
            organization_id=tenant_id,
            actor_id=actor_id,
            action=action,
            resource=resource,
            metadata=metadata or {},
            created_at=datetime.now(timezone.utc)
        )
        # Directly bypass soft-delete mechanics on persistence explicitly
        log.save()
        
        # Fire downstream alert stream
        from services.event_bus import event_bus
        try:
            event_bus.publish("audit.event.recorded", {
                "tenant_id": tenant_id,
                "action": action,
                "resource": resource
            })
        except:
            pass
