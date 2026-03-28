from . import form_bp
from flasgger import swag_from
import csv
import io
import json
import zipfile
from datetime import datetime
from routes.v1.form.helper import get_current_user, has_form_permission
from routes.v1.form import form_bp
from flask import Response, request, jsonify
from flask_jwt_extended import jwt_required
from mongoengine import DoesNotExist
from models import Form
from models import Form, FormResponse
from logger.unified_logger import app_logger, error_logger, audit_logger


# -------------------- Helper for Streaming Export --------------------
def stream_form_csv(form, responses, version_id=None):
    """
    Generates CSV content row by row for streaming responses.
    """
    from models.Form import FormVersion
    
    headers = ["response_id", "submitted_by", "submitted_at", "status"]
    field_mapping = []  # List of {var_name, label}

    # Resolve Version Snapshot
    version_doc = None
    if version_id:
        version_doc = FormVersion.objects(id=version_id, form=form.id).first()
    elif form.active_version:
        version_doc = FormVersion.objects(id=form.active_version_id, form=form.id).first()

    if version_doc:
        snapshot = version_doc.resolved_snapshot
        sections = snapshot.get("sections", [])
        for section in sections:
            prefix = f"{section.get('title')} - " if len(sections) > 1 else ""
            for question in section.get("questions", []):
                var_name = question.get("variable_name")
                if var_name:
                    headers.append(f"{prefix}{question.get('label')}")
                    field_mapping.append({"var_name": var_name})
    else:
        headers.append("data (raw)")

    # Yield header
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    yield output.getvalue()
    output.truncate(0)
    output.seek(0)

    for r in responses:
        row = [
            str(r.id),
            r.submitted_by,
            r.submitted_at.isoformat() if r.submitted_at else "",
            r.status or "submitted",
        ]

        if not version_doc:
            row.append(json.dumps(r.data))
        else:
            for mapping in field_mapping:
                var_name = mapping["var_name"]
                val = r.data.get(var_name, "")
                if isinstance(val, (list, dict)):
                    val = json.dumps(val)
                row.append(val)

        writer.writerow(row)
        yield output.getvalue()
        output.truncate(0)
        output.seek(0)


# -------------------- Export to CSV --------------------
@form_bp.route("/<form_id>/export/csv", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def export_responses_csv(form_id):
    app_logger.info(f"Entering export_responses_csv for form_id: {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id, organization_id=current_user.organization_id)
        
        if not has_form_permission(current_user, form, "view_responses"):
            app_logger.warning(f"Unauthorized CSV export attempt for form_id: {form_id} by user: {getattr(current_user, 'id', 'unknown')}")
            return error_response(message="Unauthorized to export", status_code=403)

        # Use iterator() for memory efficiency in MongoDB
        responses = FormResponse.objects(form=form.id, organization_id=current_user.organization_id).no_cache().timeout(False)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        audit_logger.info(f"CSV streaming export initiated for form_id: {form_id} by user: {current_user.id}")
        
        return Response(
            stream_form_csv(form, responses),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment;filename=form_{form_id}_{timestamp}.csv",
                "X-Content-Type-Options": "nosniff"
            },
        )
    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Error in export_responses_csv for form_id {form_id}: {str(e)}")
        return error_response(message="Internal server error", status_code=500)


def stream_form_json(form, responses):
    """
    Generates JSON content iteratively for streaming responses.
    """
    metadata = {
        "id": str(form.id),
        "title": form.title,
        "slug": form.slug,
        "created_by": form.created_by,
        "created_at": str(form.created_at),
        "status": form.status,
        "is_public": form.is_public,
        "organization_id": form.organization_id
    }
    
    yield '{"form_metadata": ' + json.dumps(metadata) + ', "responses": ['
    
    first = True
    for r in responses:
        if not first:
            yield ","
        yield json.dumps(r.to_dict(), default=str)
        first = False
        
    yield "]}"


@form_bp.route("/<form_id>/export/json", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def export_form_with_responses(form_id):
    app_logger.info(f"Entering export_form_with_responses for form_id: {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id, organization_id=current_user.organization_id)
        
        if not has_form_permission(current_user, form, "view_responses"):
            app_logger.warning(f"Unauthorized JSON export attempt for form_id: {form_id} by user: {getattr(current_user, 'id', 'unknown')}")
            return error_response(message="Unauthorized", status_code=403)

        responses = FormResponse.objects(form=form.id, organization_id=current_user.organization_id).no_cache().timeout(False)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audit_logger.info(f"JSON streaming export initiated for form_id: {form_id} by user: {current_user.id}")
        
        return Response(
            stream_form_json(form, responses),
            mimetype="application/json",
            headers={
                "Content-Disposition": f"attachment;filename=form_{form_id}_{timestamp}.json"
            },
        )
    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Error in export_form_with_responses for form_id {form_id}: {str(e)}")
        return error_response(message="Internal server error", status_code=500)


from utils.response_helper import success_response, error_response

# -------------------- Bulk Export --------------------
@form_bp.route("/export/bulk", methods=["POST"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "202": {
            "description": "Bulk export job accepted"
        }
    }
})
@jwt_required()
def export_bulk_responses():
    """Initiates an asynchronous bulk export job."""
    app_logger.info("Entering export_bulk_responses (async)")
    try:
        data = request.get_json()
        form_ids = data.get("form_ids", [])
        if not form_ids:
            app_logger.warning("Bulk export failed: Missing form_ids")
            return error_response(message="Missing form_ids", status_code=400)

        current_user = get_current_user()
        from models.Response import BulkExport
        from tasks.form_tasks import async_bulk_export

        job = BulkExport(
            organization_id=current_user.organization_id,
            form_ids=form_ids,
            created_by=str(current_user.id),
            status="pending"
        )
        job.save()

        # Trigger Celery task
        async_bulk_export.delay(str(job.id), current_user.organization_id)

        audit_logger.info(f"Async bulk export job {job.id} initiated by user {current_user.id}")
        return success_response(
            data={"job_id": str(job.id), "status": job.status},
            message="Bulk export job accepted",
            status_code=202
        )
    except Exception as e:
        error_logger.error(f"Error initiating bulk export: {str(e)}")
        return error_response(message=str(e), status_code=400)


@form_bp.route("/export/bulk/<job_id>", methods=["GET"])
@jwt_required()
def get_bulk_export_status(job_id):
    """Checks status of a bulk export job."""
    try:
        current_user = get_current_user()
        from models.Response import BulkExport
        job = BulkExport.objects.get(id=job_id, organization_id=current_user.organization_id)
        
        result = {
            "job_id": str(job.id),
            "status": job.status,
            "created_at": job.created_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error_message": job.error_message
        }
        return success_response(data=result)
    except DoesNotExist:
        return error_response(message="Job not found", status_code=404)


@form_bp.route("/export/bulk/<job_id>/download", methods=["GET"])
@jwt_required()
def download_bulk_export(job_id):
    """Downloads the completed bulk export file."""
    try:
        current_user = get_current_user()
        from models.Response import BulkExport
        job = BulkExport.objects.get(id=job_id, organization_id=current_user.organization_id)
        
        if job.status != "completed":
            return error_response(message=f"Job is in {job.status} state", status_code=400)
            
        if not job.file_binary:
            return error_response(message="Export file not found", status_code=404)

        timestamp = job.completed_at.strftime("%Y%m%d_%H%M%S") if job.completed_at else "completed"
        return Response(
            job.file_binary,
            mimetype="application/zip",
            headers={
                "Content-Disposition": f"attachment;filename=bulk_export_{timestamp}.zip"
            },
        )
    except DoesNotExist:
        return error_response(message="Job not found", status_code=404)

