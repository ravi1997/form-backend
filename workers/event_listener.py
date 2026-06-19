import threading
from app import create_app
from services import event_bus
from models import Form
from tasks.notification_tasks import process_notification_triggers
from services.vector_provider import vector_provider
from services.search_service import search_service
from logger.unified_logger import app_logger, error_logger, audit_logger


def handle_form_submitted(payload: dict):
    """
    Consumer logic for the 'form.submitted' event.
    Re-couples the background asynchronous processing (Webhooks, Emails, SMS)
    without burdening the synchronous web tier.
    """
    form_id = payload.get("form_id")
    response_id = payload.get("response_id")
    organization_id = payload.get("organization_id")

    app_logger.info(f"Entering handle_form_submitted: response_id={response_id}")

    try:
        # Evict Analysis Board caches targeting this form
        if form_id and organization_id:
            try:
                from services.analysis_board_service import AnalysisBoardService

                AnalysisBoardService.evict_caches_for_form(form_id, organization_id)
            except Exception as evict_err:
                error_logger.error(
                    f"Failed to evict analysis board caches during form.submitted handling: {evict_err}"
                )

        form = Form.objects(id=form_id, is_deleted=False).first()
        if form and form.triggers:
            triggers_data = [
                t.to_mongo().to_dict() for t in form.triggers if t.is_active
            ]
            if triggers_data:
                process_notification_triggers.delay(triggers_data, payload)
                app_logger.info(
                    f"Delegated {len(triggers_data)} triggers to Celery for {response_id}"
                )

        # Check project-bound automated reports threshold triggers
        project_ref = None
        if form:
            try:
                project_ref = form.project
            except Exception:
                pass

        if project_ref:
            try:
                from models.form import Project
                from tasks.report_tasks import async_generate_report

                proj = Project.objects(
                    id=str(project_ref.id), is_deleted=False
                ).first()
                if proj and proj.report_configs:
                    updated = False
                    for cfg in proj.report_configs:
                        if cfg.trigger_type == "threshold" and cfg.threshold_limit:
                            cfg.current_threshold_counter += 1
                            updated = True
                            if cfg.current_threshold_counter >= cfg.threshold_limit:
                                app_logger.info(
                                    f"Report Config threshold hit ({cfg.threshold_limit}) for config {cfg.id}!"
                                )
                                async_generate_report.delay(
                                    str(proj.id),
                                    str(cfg.id),
                                    f"Threshold Hit ({cfg.threshold_limit})",
                                )
                                cfg.current_threshold_counter = 0
                    if updated:
                        proj.save()
            except Exception as report_trigger_err:
                error_logger.error(
                    f"Failed to process automated report threshold trigger: {report_trigger_err}"
                )

        # Check and trigger ApprovalWorkflows
        if form_id and organization_id and response_id:
            try:
                from models.workflow import Workflow as ApprovalWorkflow
                from models.workflow import WorkflowInstance
                
                active_wf = ApprovalWorkflow.objects(
                    trigger_form_id=str(form_id),
                    organization_id=organization_id,
                    status="active",
                    is_deleted=False
                ).first()
                
                if active_wf:
                    existing_wf_instance = WorkflowInstance.objects(
                        resource_type="form_response",
                        resource_id=str(response_id),
                        organization_id=organization_id,
                        is_deleted=False
                    ).first()
                    
                    if not existing_wf_instance:
                        wf_instance = WorkflowInstance(
                            organization_id=organization_id,
                            workflow_definition=active_wf,
                            resource_type="form_response",
                            resource_id=str(response_id),
                            status="pending",
                            current_step_order=1,
                            step_approvals={}
                        )
                        wf_instance.save()
                        
                        from models.response import FormResponse
                        response = FormResponse.objects(id=response_id).first()
                        if response:
                            response.review_status = "pending"
                            response.save()
                            
                        app_logger.info(
                            f"Automatically started workflow instance {wf_instance.id} for response {response_id}"
                        )
            except Exception as wf_trigger_err:
                error_logger.error(
                    f"Failed to auto-trigger workflow instance: {wf_trigger_err}"
                )

        audit_logger.info(
            f"Event 'form.submitted' processed for response_id={response_id}"
        )
        app_logger.info(f"Exiting handle_form_submitted: {response_id}")
    except Exception as e:
        error_logger.error(
            f"Error handling form.submitted event for {response_id}: {e}"
        )


def handle_form_indexed(payload: dict):
    """
    Consumer logic for 'form.indexed'.
    Synchronizes the MongoDB truth to Elasticsearch entirely out-of-band.
    """
    form_id = payload.get("id")
    app_logger.info(f"Entering handle_form_indexed: form_id={form_id}")
    try:
        search_service.index_form(payload)
        # Simultaneously vectorize for RAG if configured
        vector_provider.embed_and_store(
            tenant_id=payload.get("organization_id", "unknown"),
            document_id=form_id,
            text=str(payload),
        )
        audit_logger.info(f"Event 'form.indexed' processed for form_id={form_id}")
        app_logger.info(f"Exiting handle_form_indexed: {form_id}")
    except Exception as e:
        error_logger.error(f"Error handling form.indexed event for {form_id}: {e}")


def start_consumers():
    """Blocking loop to consume Redis PubSub events."""
    app = create_app()
    with app.app_context():
        app_logger.info("Initializing Redis EventBus listeners...")
        listeners = [
            ("form.submitted", handle_form_submitted),
            ("form.indexed", handle_form_indexed),
        ]
        threads = []
        for topic, handler in listeners:
            thread = threading.Thread(
                target=event_bus.subscribe,
                args=(topic, handler),
                daemon=True,
            )
            thread.start()
            threads.append(thread)

        app_logger.info(f"Started {len(threads)} consumer threads")
        for thread in threads:
            thread.join()


if __name__ == "__main__":
    start_consumers()
