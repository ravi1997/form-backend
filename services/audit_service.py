from models.AuditLog import AuditLog
from datetime import datetime, timezone
from flask import has_request_context, request, g
from logger.unified_logger import app_logger, error_logger, audit_logger


class AuditService:
    @staticmethod
    def append_event(
        tenant_id: str,
        actor_id: str,
        action: str,
        resource: str,
        metadata: dict = None,
        resource_type: str = None,
        resource_id: str = None
    ):
        """
        Enforces Append-Only immutability rules. Automatically enriches the
        log payload with request correlation context (IP, User-Agent, Request ID)
        if executed within an active request lifecycle.
        """
        app_logger.debug(
            f"Entering append_event: tenant={tenant_id}, actor={actor_id}, action={action}, resource={resource}"
        )
        try:
            # Automatic correlation context
            ip_addr = None
            u_agent = None
            req_id = getattr(metadata, "request_id", None) if metadata else None

            if has_request_context():
                if not req_id:
                    req_id = getattr(g, "request_id", None) or request.headers.get("X-Request-ID")
                
                # Fetch remote IP supporting load balancer header
                ip_addr = request.headers.get("X-Forwarded-For", request.remote_addr)
                if ip_addr and "," in ip_addr:
                    ip_addr = ip_addr.split(",")[0].strip()
                u_agent = request.user_agent.string

            # Backward-compatible resource type resolution
            resolved_type = resource_type
            resolved_id = resource_id
            if not resolved_type and resource and ":" in resource:
                parts = resource.split(":", 1)
                resolved_type = parts[0]
                resolved_id = parts[1]
            elif not resolved_type:
                resolved_type = resource

            log = AuditLog(
                organization_id=tenant_id,
                actor_id=actor_id,
                action=action,
                resource_type=resolved_type,
                resource_id=resolved_id,
                ip_address=ip_addr,
                user_agent=u_agent,
                request_id=req_id,
                metadata=metadata or {},
                timestamp=datetime.now(timezone.utc),
            )
            # Bypass soft-delete mechanics on persistence
            log.save()

            audit_logger.info(
                f"Audit event recorded: {action} on {resolved_type}:{resolved_id} by {actor_id} in tenant {tenant_id} (req={req_id})"
            )

            # Fire downstream alert stream
            from services.event_bus import event_bus

            try:
                event_bus.publish(
                    "audit.event.recorded",
                    {
                        "tenant_id": tenant_id,
                        "action": action,
                        "resource_type": resolved_type,
                        "resource_id": resolved_id,
                        "request_id": req_id
                    },
                )
            except Exception as e:
                error_logger.error(
                    f"Failed to publish audit event to event bus: {str(e)}"
                )

            app_logger.debug(f"Exiting append_event successfully")
        except Exception as e:
            error_logger.error(f"Failed to append audit event: {str(e)}", exc_info=True)
            raise
