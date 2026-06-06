from config.celery import celery_app
from services.compliance_service import ComplianceService
from logger.unified_logger import app_logger, error_logger, audit_logger
import csv
import json
import os
from uuid import uuid4
from models.AuditLog import AuditLog


@celery_app.task(bind=True, max_retries=3, default_retry_delay=3600)
def execute_tenant_retention_policy(self, organization_id: str, actor_id: str = "system"):
    """
    Automated retention scrubbing task for a specific tenant.
    """
    app_logger.info(f"Starting retention scrubbing for tenant: {organization_id}")
    try:
        service = ComplianceService()
        result = service.execute_retention_policy(organization_id, actor_id)
        app_logger.info(
            f"Retention scrubbing completed for tenant: {organization_id}. "
            f"Pruned: {result['pruned_count']}, Held: {result['held_count']}"
        )
        return result
    except Exception as e:
        error_logger.error(f"Retention scrubbing failed for tenant {organization_id}: {e}", exc_info=True)
        raise self.retry(exc=e)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def export_tenant_audit_logs_task(self, organization_id: str, format: str = "csv"):
    """
    Background task to package and backup tenant audit trails.
    Saves file as audit_export_{organization_id}_{export_uuid}.{format}
    """
    app_logger.info(f"Starting audit log export for tenant: {organization_id} in format: {format}")
    try:
        logs = AuditLog.objects(organization_id=organization_id, is_deleted=False).order_by("-timestamp")
        
        export_dir = "/app/logs/exports"
        os.makedirs(export_dir, exist_ok=True)
        
        export_uuid = str(uuid4())
        filename = f"audit_export_{organization_id}_{export_uuid}.{format}"
        file_path = os.path.join(export_dir, filename)
        
        if format.lower() == "csv":
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "id", "timestamp", "actor_id", "action", "resource_type", 
                    "resource_id", "ip_address", "user_agent", "request_id"
                ])
                for log in logs:
                    writer.writerow([
                        str(log.id),
                        log.timestamp.isoformat() if log.timestamp else "",
                        log.actor_id,
                        log.action,
                        log.resource_type or "",
                        log.resource_id or "",
                        log.ip_address or "",
                        log.user_agent or "",
                        log.request_id or ""
                    ])
        else:
            # json format
            records = []
            for log in logs:
                records.append({
                    "id": str(log.id),
                    "timestamp": log.timestamp.isoformat() if log.timestamp else "",
                    "actor_id": log.actor_id,
                    "action": log.action,
                    "resource_type": log.resource_type,
                    "resource_id": log.resource_id,
                    "ip_address": log.ip_address,
                    "user_agent": log.user_agent,
                    "request_id": log.request_id,
                    "metadata": log.metadata
                })
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
                
        app_logger.info(f"Audit log export complete for tenant {organization_id}: {file_path}")
        return {
            "status": "SUCCESS",
            "filename": filename,
            "export_uuid": export_uuid,
            "count": len(logs)
        }
    except Exception as e:
        error_logger.error(f"Audit log export failed for tenant {organization_id}: {e}", exc_info=True)
        raise self.retry(exc=e)

