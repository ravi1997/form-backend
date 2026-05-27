from config.celery import celery_app
from services.report_compiler_service import ReportCompilerService
from logger.unified_logger import app_logger, error_logger

@celery_app.task(name="tasks.report_tasks.async_generate_report")
def async_generate_report(project_id: str, config_id: str, trigger_reason: str = "Cron Schedule"):
    """
    Asynchronously executes, compiles and distributes automated custom PDF/HTML reports.
    """
    app_logger.info(f"Celery task async_generate_report started for project {project_id}, config {config_id}")
    try:
        compiler = ReportCompilerService()
        file_url = compiler.compile_report(project_id, config_id, trigger_reason)
        
        # In a real environment, this delegates emails with pdf attachments to processed queues:
        # from tasks.services import process_mail
        # process_mail.delay(...)
        
        app_logger.info(f"Celery task succeeded. Report URL: {file_url}")
        return file_url
    except Exception as e:
        error_logger.error(f"Celery task failed to generate report: {str(e)}")
        raise
