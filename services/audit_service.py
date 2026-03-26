from models.AuditLog import AuditLog
from datetime import datetime, timezone
from schemas.base import InboundPayloadSchema
from schemas.response import FormResponseSchema # Reused generically here for DTO compliance
from logger.unified_logger import app_logger, error_logger, audit_logger

class AuditService:
    @staticmethod
    def append_event(tenant_id: str, actor_id: str, action: str, resource: str, metadata: dict = None):
        """
        [Phase 13: Compliance and Audit System]
        Enforces Append-Only immutability rules. Existing documents are
        never queried or updated by this service boundary.
        """
        app_logger.debug(f"Entering append_event: tenant={tenant_id}, actor={actor_id}, action={action}, resource={resource}")
        try:
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
            
            audit_logger.info(f"Audit event recorded: {action} on {resource} by {actor_id} in tenant {tenant_id}")
            
            # Fire downstream alert stream
            from services.event_bus import event_bus
            try:
                event_bus.publish("audit.event.recorded", {
                    "tenant_id": tenant_id,
                    "action": action,
                    "resource": resource
                })
            except Exception as e:
                error_logger.error(f"Failed to publish audit event to event bus: {str(e)}")
                
            app_logger.debug(f"Exiting append_event successfully")
        except Exception as e:
            error_logger.error(f"Failed to append audit event: {str(e)}", exc_info=True)
            raise
