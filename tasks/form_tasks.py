from config.celery import celery_app
from services.form_service import FormService
from logger.unified_logger import app_logger, error_logger, audit_logger
from models.Form import Form
from models.User import User
import uuid

form_service = FormService()

@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def async_clone_form(self, form_id, user_id, organization_id, new_title=None, new_slug=None):
    """
    Background task to clone a form.
    """
    app_logger.info(f"Entering async_clone_form: form_id={form_id}, user_id={user_id}, organization_id={organization_id}")
    try:
        original = Form.objects.get(id=form_id, is_deleted=False)
        
        # Double check organization match for security
        if original.organization_id != organization_id:
            error_logger.error(f"Tenant violation in async_clone_form: Form {form_id} org {original.organization_id} vs user org {organization_id}")
            return {"status": "error", "message": "Tenant violation"}

        final_slug = new_slug or f"{original.slug}-copy-{uuid.uuid4().hex[:6]}"
        final_title = new_title or f"Copy of {original.title}"

        new_form = Form(
            title=final_title,
            slug=final_slug,
            description=original.description,
            created_by=user_id,
            organization_id=organization_id,
            status="draft",
            is_public=False,
            is_template=original.is_template,
            tags=original.tags,
            editors=[user_id],
            sections=original.sections, # This handles the deep copy if MongoEngine supports it
            questions=original.questions
        )
        new_form.save()
        
        audit_logger.info(f"Form {form_id} cloned to {new_form.id} via background task. Action by User {user_id} for Org {organization_id}")
        app_logger.info(f"Exiting async_clone_form: successfully cloned {form_id} to {new_form.id}")
        return {"status": "success", "form_id": str(new_form.id), "slug": final_slug}
        
    except Exception as e:
        error_logger.error(f"Task async_clone_form failed for {form_id}: {str(e)}", exc_info=True)
        raise self.retry(exc=e)

@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
def async_publish_form(self, form_id, organization_id, major_bump=False, minor_bump=True):
    """
    Background task to publish a form (semantic versioning and snapshotting).
    """
    app_logger.info(f"Entering async_publish_form: form_id={form_id}, organization_id={organization_id}")
    try:
        result = form_service.publish_form(
            form_id=form_id, 
            organization_id=organization_id,
            major_bump=major_bump, 
            minor_bump=minor_bump
        )
        audit_logger.info(f"Form {form_id} published successfully via background task. Org: {organization_id}")
        app_logger.info(f"Exiting async_publish_form: successfully published {form_id}")
        return {"status": "success", "form_id": str(result.id)}
    except Exception as e:
        error_logger.error(f"Task async_publish_form failed for {form_id}: {str(e)}", exc_info=True)
        raise self.retry(exc=e)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def async_recalculate_materialized_view(self, view_id, organization_id):
    """
    Background task to execute a DynamicViewDefinition pipeline
    and store the results in a SummarySnapshot for fast retrieval.
    """
    from services.response_service import DynamicViewService
    from models.Response import SummarySnapshot
    from datetime import datetime, timezone

    app_logger.info(f"Entering async_recalculate_materialized_view: view_id={view_id}, organization_id={organization_id}")
    try:
        service = DynamicViewService()
        view_def = service.model.objects(id=view_id, organization_id=organization_id, is_deleted=False).first()
        if not view_def:
            error_logger.error(f"View {view_id} not found for recalculation. Org: {organization_id}")
            return {"status": "error", "message": "View not found"}

        # Execute the pipeline
        results = service.execute_materialized_view(view_id)
        
        # Snapshot the results
        snapshot = SummarySnapshot(
            form_id=str(view_def.form.id) if view_def.form else "GLOBAL",
            period_start=view_def.created_at,
            period_end=datetime.now(timezone.utc),
            period_label=f"Snapshot for {view_def.view_name}",
            response_count=len(results),
            strategy_used="mongodb_aggregation_worker",
            summary_data={"results": results},
            created_by="system_worker"
        )
        snapshot.save()
        
        audit_logger.info(f"View {view_id} recalculated and snapshot {snapshot.id} created via background task. Org: {organization_id}")
        app_logger.info(f"Exiting async_recalculate_materialized_view: successfully recalculated {view_id}")
        return {"status": "success", "snapshot_id": str(snapshot.id)}
        
    except Exception as e:
        error_logger.error(f"Task async_recalculate_materialized_view failed for {view_id}: {str(e)}", exc_info=True)
        raise self.retry(exc=e)
