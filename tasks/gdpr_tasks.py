from config.celery import celery_app
from services.gdpr_compliance_service import gdpr_compliance_service
from logger.unified_logger import app_logger, error_logger, audit_logger


@celery_app.task(bind=True, max_retries=3, default_retry_delay=3600)
def prune_soft_deleted_records(
    self, collections=None, retention_days=30, dry_run=False
):
    """
    GDPR Compliance: Permanently delete soft-deleted records older than retention period.

    This task:
    - Permanently deletes (.delete()) any Forms and FormResponses where is_deleted=True
      and deleted_at is older than retention_days
    - Also cleans up old BulkExport and SummarySnapshot records
    - Is an opt-in task that should be triggered by a system administrator or scheduled Celery Beat job
    - Logs all hard deletes to audit_logger for compliance
    - Supports dry-run mode for safe testing

    Args:
        collections: List of collection types to process (default: ["forms", "responses", "bulk_exports", "snapshots"])
        retention_days: Number of days to keep soft-deleted records before hard deletion (default: 30)
        dry_run: If True, only count records without actually deleting them (for safe testing)

    Returns:
        dict: Summary of deleted records with counts per collection
    """
    app_logger.info(
        f"Starting GDPR prune: retention_days={retention_days}, dry_run={dry_run}, collections={collections}"
    )

    try:
        result = gdpr_compliance_service.prune_soft_deleted_records(
            collections=collections, retention_days=retention_days, dry_run=dry_run
        )

        audit_logger.info(
            f"GDPR prune task completed: {result['total_deleted']} records {'would be ' if dry_run else ''}permanently deleted"
        )

        app_logger.info(
            f"GDPR prune task completed: {result['total_deleted']} records {'would be ' if dry_run else ''}permanently deleted"
        )

        return result

    except Exception as e:
        error_logger.error(f"GDPR prune failed: {e}", exc_info=True)
        raise self.retry(exc=e)
