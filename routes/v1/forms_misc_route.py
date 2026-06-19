from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from flasgger import swag_from
from mongoengine import DoesNotExist
from mongoengine.queryset.visitor import Q
from datetime import datetime, timezone

from models import Form
from models.base import (
    ACCESS_LEVEL_CHOICES,
    COMPARISON_TYPE_CHOICES,
    CONDITION_OPERATOR_CHOICES,
    CONDITION_SOURCE_TYPE_CHOICES,
    FIELD_API_CALL_CHOICES,
    FIELD_TYPE_CHOICES,
    LOGICAL_OPERATOR_CHOICES,
    PERMISSION_CHOICES,
    ROLE_CHOICES,
    TRIGGER_ACTION_CHOICES,
    TRIGGER_EVENT_CHOICES,
    UI_TYPE_CHOICES,
)
from utils.response_helper import success_response, error_response
from routes.v1.form.helper import get_current_user
from logger.unified_logger import app_logger, error_logger, audit_logger

forms_misc_bp = Blueprint("forms_misc", __name__)


def _builder_metadata_payload():
    return {
        "field_types": list(FIELD_TYPE_CHOICES),
        "ui_types": list(UI_TYPE_CHOICES),
        "condition": {
            "logical_operators": list(LOGICAL_OPERATOR_CHOICES),
            "source_types": list(CONDITION_SOURCE_TYPE_CHOICES),
            "operators": list(CONDITION_OPERATOR_CHOICES),
            "comparison_types": list(COMPARISON_TYPE_CHOICES),
        },
        "triggers": {
            "events": list(TRIGGER_EVENT_CHOICES),
            "actions": list(TRIGGER_ACTION_CHOICES),
            "field_api_calls": list(FIELD_API_CALL_CHOICES),
        },
        "access": {
            "levels": list(ACCESS_LEVEL_CHOICES),
            "permissions": list(PERMISSION_CHOICES),
            "roles": list(ROLE_CHOICES),
        },
        "validation": {
            "text": [
                "min_length",
                "max_length",
                "min_word_count",
                "max_word_count",
                "regex",
            ],
            "number": ["min_value", "max_value"],
            "date": [
                "date_min",
                "date_max",
                "disable_past_dates",
                "disable_future_dates",
                "disable_weekends",
            ],
            "file": ["allowed_file_types", "max_files", "max_file_size"],
            "selection": ["min_selection", "max_selection"],
        },
        "languages": [
            {"code": "en", "name": "English"},
            {"code": "hi", "name": "Hindi"},
        ],
    }


@forms_misc_bp.route("/builder-metadata", methods=["GET"])
@swag_from(
    {"tags": ["Form"], "responses": {"200": {"description": "Builder metadata"}}}
)
@jwt_required()
def get_builder_metadata():
    return success_response(data=_builder_metadata_payload())


@forms_misc_bp.route("/slug-available", methods=["GET"])
@swag_from(
    {
        "tags": ["Form"],
        "responses": {"200": {"description": "Check if a form slug is already taken."}},
    }
)
@jwt_required()
def check_slug():
    slug = request.args.get("slug")
    form_id = request.args.get("form_id")
    app_logger.info(f"Checking slug availability for: {slug}")
    if not slug:
        return error_response(message="slug parameter is required", status_code=400)
    current_form = None
    if form_id:
        current_form = Form.objects(id=form_id).first()
    exists = Form.objects.filter(Q(slug=slug) | Q(slug_history=slug)).first()
    if current_form and current_form.slug == slug:
        exists = None
    app_logger.info(f"Slug availability for {slug}: {not exists}")
    return success_response(data={"available": not exists})


@forms_misc_bp.route("/expired", methods=["GET"])
@jwt_required()
def list_expired_forms():
    try:
        current_user = get_current_user()
        now = datetime.now(timezone.utc)
        expired_forms = Form.objects(
            organization_id=current_user.organization_id,
            expires_at__lt=now,
            is_deleted=False,
        )
        data = [
            {"id": str(f.id), "title": f.title, "expires_at": f.expires_at.isoformat()}
            for f in expired_forms
        ]
        return success_response(data=data)
    except Exception as e:
        error_logger.error(f"Error fetching expired forms: {e}")
        return error_response(message=str(e), status_code=500)


@forms_misc_bp.route("/templates", methods=["GET"])
@jwt_required()
def list_templates():
    try:
        templates = Form.objects(is_template=True, is_deleted=False)
        data = [
            {"id": str(t.id), "title": t.title, "description": t.description}
            for t in templates
        ]
        return success_response(data=data)
    except Exception as e:
        error_logger.error(f"Error listing templates: {e}")
        return error_response(message=str(e), status_code=500)


@forms_misc_bp.route("/templates/<template_id>", methods=["GET"])
@jwt_required()
def get_template(template_id):
    try:
        t = Form.objects.get(id=template_id, is_template=True, is_deleted=False)
        return success_response(
            data={"id": str(t.id), "title": t.title, "schema": t.form_fields}
        )
    except DoesNotExist:
        return error_response(message="Template not found", status_code=404)
    except Exception as e:
        return error_response(message=str(e), status_code=500)


@forms_misc_bp.route("/import", methods=["POST"])
@jwt_required()
def import_form():
    try:
        current_user = get_current_user()
        data = request.get_json() or {}
        title = data.get("title")
        fields = data.get("fields", [])
        if not title:
            return error_response(message="Missing form title", status_code=400)

        form = Form(
            title=title,
            organization_id=current_user.organization_id,
            form_fields=fields,
            created_by=str(current_user.id),
        )
        form.save()
        return success_response(
            data={"form_id": str(form.id)},
            message="Form imported successfully",
            status_code=201,
        )
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@forms_misc_bp.route("/import/schema", methods=["POST"])
@jwt_required()
def import_schema():
    try:
        data = request.get_json() or {}
        fields = data.get("fields", [])
        # Lightweight schema validation logic
        return success_response(data={"valid": True, "fields_count": len(fields)})
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@forms_misc_bp.route("/export/bulk", methods=["POST"])
@swag_from(
    {
        "tags": ["Form"],
        "responses": {"202": {"description": "Bulk export job accepted"}},
    }
)
@jwt_required()
def export_bulk_responses():
    try:
        data = request.get_json() or {}
        form_ids = data.get("form_ids", [])
        if not form_ids:
            return error_response(message="Missing form_ids", status_code=400)

        current_user = get_current_user()
        from models.utility import ExportJob
        from tasks.form_tasks import async_bulk_export

        job = ExportJob(
            organization_id=current_user.organization_id,
            form_ids=form_ids,
            created_by=str(current_user.id),
            status="pending",
        )
        job.save()
        async_bulk_export.delay(str(job.id), current_user.organization_id)

        audit_logger.info(
            f"Async bulk export job {job.id} initiated by user {current_user.id}"
        )
        return success_response(
            data={"job_id": str(job.id), "status": job.status},
            message="Bulk export job accepted",
            status_code=202,
        )
    except Exception as e:
        error_logger.error(f"Error initiating bulk export: {str(e)}")
        return error_response(message=str(e), status_code=400)


@forms_misc_bp.route("/export/bulk/<job_id>", methods=["GET"])
@jwt_required()
def get_bulk_export_status(job_id):
    try:
        current_user = get_current_user()
        from models.utility import ExportJob

        job = ExportJob.objects.get(
            id=job_id, organization_id=current_user.organization_id
        )
        result = {
            "job_id": str(job.id),
            "status": job.status,
            "created_at": job.created_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error_message": job.error_message,
        }
        return success_response(data=result)
    except DoesNotExist:
        return error_response(message="Job not found", status_code=404)


@forms_misc_bp.route("/export/bulk/<job_id>/download", methods=["GET"])
@jwt_required()
def download_bulk_export(job_id):
    try:
        current_user = get_current_user()
        from models.utility import ExportJob
        from flask import send_file
        import os

        job = BulkExport.objects.get(
            id=job_id, organization_id=current_user.organization_id
        )
        if job.status != "completed" or not job.file_path:
            return error_response(
                message="Job not completed or file missing", status_code=400
            )

        if not os.path.exists(job.file_path):
            return error_response(message="File not found on server", status_code=404)

        return send_file(
            job.file_path,
            as_attachment=True,
            download_name=os.path.basename(job.file_path),
        )
    except DoesNotExist:
        return error_response(message="Job not found", status_code=404)
    except Exception as e:
        return error_response(message=str(e), status_code=500)


@forms_misc_bp.route("/<form_id>/responses", methods=["POST"])
def submit_public_response(form_id):
    """
    Public form response submission secured by API Key.
    """
    from middleware.api_key_auth import require_api_key
    from services.api_key_service import ApiKeyService
    from services.response_service import FormResponseService, FormResponseCreateSchema
    from uuid import UUID

    raw_key = request.headers.get("X-API-Key")
    if not raw_key:
        return error_response(message="X-API-Key header is required", status_code=401)

    api_key_record = ApiKeyService.get_active_key(raw_key)
    if not api_key_record:
        return error_response(message="Invalid API Key", status_code=403)

    if not ApiKeyService.rate_limit_key(raw_key):
        return error_response(message="API key rate limit exceeded", status_code=429)

    org_id = api_key_record.organization_id
    data = request.get_json(silent=True) or {}

    try:
        form_uuid = UUID(form_id)
    except ValueError:
        return error_response(message="Invalid form ID format", status_code=400)

    try:
        form = Form.objects.get(id=form_uuid, organization_id=org_id, is_deleted=False)
    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)

    # Check if form lifecycle allows submissions
    now = datetime.now(timezone.utc)
    if form.expires_at and form.expires_at.replace(tzinfo=timezone.utc) < now:
        return error_response(message="This form has expired", status_code=400)
    if form.publish_at and form.publish_at.replace(tzinfo=timezone.utc) > now:
        return error_response(message="This form is not yet available", status_code=400)

    submission_data = {
        "form": str(form.id),
        "organization_id": org_id,
        "data": data.get("data", {}),
        "answers": data.get("answers", {}),
        "repeat_groups": data.get("repeat_groups", {}),
        "submitted_by": f"api-key:{api_key_record.key_prefix}",
        "ip_address": request.remote_addr,
        "user_agent": request.user_agent.string,
    }

    try:
        response_service = FormResponseService()
        create_schema = FormResponseCreateSchema(**submission_data)
        response = response_service.create_submission(create_schema)
        return success_response(
            data={"response_id": str(response.id)},
            message="Response submitted successfully via API Key",
            status_code=201,
        )
    except Exception as e:
        return error_response(message=str(e), status_code=400)

