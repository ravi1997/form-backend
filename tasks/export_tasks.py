from config.celery import celery_app
from logger.unified_logger import app_logger, error_logger
from services.export_job_service import export_job_service
from services.analysis_run_service import analysis_run_service
from services.storage_backend import export_storage_backend


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def generate_analysis_export_task(
    self,
    export_job_id: str,
    export_format: str,
    organization_id: str = None,
    analysis_run_id: str = None,
    node_ids=None,
):
    app_logger.info(
        f"Starting generate_analysis_export_task export_job_id={export_job_id} export_format={export_format}"
    )
    job = None
    try:
        job = export_job_service.get_job(export_job_id, organization_id=organization_id)
        if not job:
            raise ValueError("Export job metadata not found")

        if job.status == "completed" and job.file_path and export_storage_backend.exists(job.file_path):
            return {
                "status": "completed",
                "export_job_id": str(job.id),
                "file_path": job.file_path,
            }

        export_job_service.transition_status(job, "processing")
        job.idempotency_key = job.idempotency_key or f"{job.analysis_run_id}:{export_format}:{job.organization_id}"
        job.save()

        generated_path, generated_size = analysis_run_service.generate_analysis_export(
            run_id=analysis_run_id or job.analysis_run_id,
            organization_id=organization_id or job.organization_id,
            export_format=export_format,
            node_ids=node_ids or job.node_ids,
            analysis_id=job.analysis_run_id,
        )
        export_job_service.attach_file_path(job, generated_path, generated_size)
        return {
            "status": "completed",
            "export_job_id": str(job.id),
            "file_path": generated_path,
        }
    except Exception as exc:
        error_logger.error(
            f"generate_analysis_export_task failed for export_job_id={export_job_id}: {exc}",
            exc_info=True,
        )
        if job:
            export_job_service.record_failure(job, str(exc))
        raise self.retry(exc=exc)
