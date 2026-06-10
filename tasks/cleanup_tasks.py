from config.celery import celery_app
from logger.unified_logger import app_logger, error_logger
from services.export_retention_service import export_retention_service


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
def cleanup_analysis_exports_task(self):
    app_logger.info("Starting cleanup_analysis_exports_task")
    try:
        result = export_retention_service.prune_expired_exports()
        app_logger.info(
            f"cleanup_analysis_exports_task completed. deleted={result['deleted']} missing={result['missing']}"
        )
        return result
    except Exception as exc:
        error_logger.error(
            f"cleanup_analysis_exports_task failed: {exc}", exc_info=True
        )
        raise self.retry(exc=exc)
