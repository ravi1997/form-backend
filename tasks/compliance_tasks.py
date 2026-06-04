from config.celery import celery_app
from services.compliance_service import ComplianceService
from logger.unified_logger import app_logger, error_logger, audit_logger


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
