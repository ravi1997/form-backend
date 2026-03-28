from config.celery import celery_app
from services.form_service import FormService
from logger.unified_logger import app_logger, error_logger, audit_logger
from models.Form import Form
from models.User import User
import uuid

form_service = FormService()

def _deep_clone_section(original_section):
    """Recursively clones sections and their embedded questions."""
    from models.Form import Section
    
    # Create a new section document with a new ID
    new_section = Section(
        title=original_section.title,
        description=original_section.description,
        help_text=original_section.help_text,
        order=original_section.order,
        logic=original_section.logic,
        ui=original_section.ui,
        questions=original_section.questions, # EmbeddedDocuments are deep-copied by default in MongoEngine assignments
        tags=original_section.tags,
        meta_data=original_section.meta_data,
        response_templates=original_section.response_templates
    )
    
    # Recursively clone sub-sections
    if original_section.sections:
        new_section.sections = [_deep_clone_section(s) for s in original_section.sections]
        
    new_section.save()
    return new_section

@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def async_clone_form(self, form_id, user_id, organization_id, new_title=None, new_slug=None):
    """
    Background task to clone a form with full deep-copy of sections.
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

        # Deep clone all sections
        new_sections = [_deep_clone_section(s) for s in original.sections]

        new_form = Form(
            title=final_title,
            slug=final_slug,
            description=original.description,
            help_text=original.help_text,
            created_by=user_id,
            organization_id=organization_id,
            status="draft",
            is_public=False,
            is_template=original.is_template,
            tags=original.tags,
            editors=[user_id],
            sections=new_sections,
            style=original.style,
            response_templates=original.response_templates,
            triggers=original.triggers
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

@celery_app.task(bind=True, max_retries=1)
def async_bulk_export(self, job_id, organization_id):
    """
    Background task to generate a bulk export ZIP file.
    """
    from models.Response import BulkExport, FormResponse
    from models.Form import Form
    from routes.v1.form.export import generate_form_csv # We should move this to a service eventually
    import io
    import zipfile
    from datetime import datetime, timezone
    from mongoengine import DoesNotExist

    app_logger.info(f"Entering async_bulk_export: job_id={job_id}, organization_id={organization_id}")
    
    job = BulkExport.objects(id=job_id, organization_id=organization_id).first()
    if not job:
        error_logger.error(f"BulkExport job {job_id} not found. Org: {organization_id}")
        return

    job.status = "processing"
    job.save()

    try:
        zip_buffer = io.BytesIO()
        exported_count = 0
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for fid in job.form_ids:
                try:
                    # Enforce tenant isolation
                    form = Form.objects.get(id=fid, organization_id=organization_id)
                    responses = FormResponse.objects(form=form.id, organization_id=organization_id).no_cache()
                    
                    # Using the streaming generator logic but fully consuming it for the zip
                    # (Better to have a unified helper)
                    from routes.v1.form.export import stream_form_csv
                    csv_content = "".join(list(stream_form_csv(form, responses)))

                    safe_title = "".join([c for c in form.title if c.isalnum() or c in (" ", "_", "-")]).strip()
                    filename = f"{safe_title}_{fid[:8]}.csv"
                    zip_file.writestr(filename, csv_content)
                    exported_count += 1
                except DoesNotExist:
                    continue
                except Exception as e:
                    app_logger.warning(f"Failed to export form {fid} in bulk job {job_id}: {e}")

        if exported_count == 0:
            job.status = "failed"
            job.error_message = "No forms were accessible for export"
            job.save()
            return

        job.file_binary = zip_buffer.getvalue()
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        job.save()
        
        app_logger.info(f"BulkExport job {job_id} completed successfully. Exported {exported_count} forms.")

    except Exception as e:
        error_logger.error(f"BulkExport job {job_id} failed: {str(e)}", exc_info=True)
        job.status = "failed"
        job.error_message = str(e)
        job.save()

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
