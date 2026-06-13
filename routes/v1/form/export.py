from . import form_bp
from flasgger import swag_from
import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from routes.v1.form.helper import get_current_user, has_form_permission
from routes.v1.form import form_bp
from flask import Response, request, jsonify
from flask_jwt_extended import jwt_required
from mongoengine import DoesNotExist
from models import Form
from models import Form, FormResponse
from logger.unified_logger import app_logger, error_logger, audit_logger
from extensions import limiter
from config.settings import settings
from utils.sensitive_data_redaction import safe_log_info, safe_log_error


def _response_data(response):
    if hasattr(response, "get_decrypted_data"):
        try:
            return response.get_decrypted_data()
        except Exception:
            pass
    if hasattr(response, "data"):
        return dict(getattr(response, "data") or {})
    return {}


def _anonymization_settings(form):
    export_settings = getattr(form, "data_export_settings", None) or {}
    if hasattr(export_settings, "model_dump"):
        export_settings = export_settings.model_dump(
            exclude_unset=True, exclude_none=True
        )
    anonymization = dict(export_settings.get("anonymization") or {})
    anonymization.setdefault("mode", "none")
    anonymization.setdefault("fields", [])
    anonymization["fields"] = {
        str(field).strip()
        for field in anonymization.get("fields") or []
        if str(field).strip()
    }
    return anonymization


def _mask_json_value(value, mode: str):
    if value is None:
        return None
    if mode == "remove":
        return None
    if mode == "hash":
        import hashlib

        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    if isinstance(value, (list, dict)):
        return "[REDACTED]"
    text = str(value)
    if len(text) <= 4:
        return "****"
    return f"{text[:2]}****{text[-2:]}"


def _format_export_datetime(value, csv_defaults: dict):
    if not value:
        return ""
    if not isinstance(value, datetime):
        return str(value)
    dt_value = value
    if dt_value.tzinfo is None:
        dt_value = dt_value.replace(tzinfo=timezone.utc)
    timezone_name = csv_defaults.get("timezone") or "UTC"
    try:
        dt_value = dt_value.astimezone(ZoneInfo(timezone_name))
    except Exception:
        dt_value = dt_value.astimezone(timezone.utc)
    date_format = (csv_defaults.get("date_format") or "iso8601").strip().lower()
    if date_format in {"iso", "iso8601"}:
        return dt_value.isoformat()
    try:
        return dt_value.strftime(csv_defaults.get("date_format"))
    except Exception:
        return dt_value.isoformat()


def _attachment_field_names(version_doc) -> set[str]:
    attachment_types = {
        "file_upload",
        "multi_file_upload",
        "multi-file_upload",
        "signature",
        "signature_pad",
    }
    attachment_fields: set[str] = set()
    if not version_doc:
        return attachment_fields

    try:
        snapshot = version_doc.resolved_snapshot or {}
    except Exception:
        snapshot = {}

    def walk(sections):
        for section in sections or []:
            if not isinstance(section, dict):
                continue
            for question in section.get("questions", []) or []:
                if not isinstance(question, dict):
                    continue
                field_type = str(
                    question.get("field_type")
                    or question.get("fieldType")
                    or ""
                ).strip()
                variable_name = str(
                    question.get("variable_name")
                    or question.get("variableName")
                    or ""
                ).strip()
                if field_type in attachment_types and variable_name:
                    attachment_fields.add(variable_name)
            nested_sections = section.get("sections", []) or []
            if nested_sections:
                walk(nested_sections)

    walk(snapshot.get("sections", []))
    return attachment_fields


# -------------------- Helper for Streaming Export --------------------
def stream_form_csv(form, responses, version_id=None):
    """
    Generates CSV content row by row for streaming responses.
    """
    from models.Form import FormVersion

    # Resolve Version Snapshot
    version_doc = None
    if version_id:
        version_doc = FormVersion.objects(id=version_id, form=form.id).first()
    else:
        active_version_id = getattr(form, "active_version_id", None)
        if active_version_id is None and hasattr(form, "_data"):
            active_version_id = form._data.get("active_version")
        if active_version_id:
            version_doc = FormVersion.objects(
                id=active_version_id, form=form.id
            ).first()
        if version_doc is None:
            version_doc = (
                FormVersion.objects(form=form.id)
                .order_by("-created_at")
                .first()
            )

    export_settings = {}
    if isinstance(getattr(form, "data_export_settings", None), dict):
        export_settings = dict(form.data_export_settings)
    elif version_doc:
        try:
            snapshot = version_doc.resolved_snapshot or {}
        except Exception:
            snapshot = {}
        if isinstance(snapshot.get("data_export_settings"), dict):
            export_settings = dict(snapshot["data_export_settings"])

    csv_defaults = export_settings.get("csv_defaults") or {}
    delimiter = csv_defaults.get("delimiter") or ","
    header_mode = (csv_defaults.get("header_mode") or "labels").strip().lower()
    empty_field_value = csv_defaults.get("empty_field_value", "")
    anonymization = export_settings.get("anonymization") or {}
    anonymized_fields = set(anonymization.get("fields") or [])
    anonymization_mode = (anonymization.get("mode") or "none").strip().lower()
    field_mapping = export_settings.get("field_mapping") or {}
    include_attachments = bool(
        csv_defaults.get("include_attachments")
        if "include_attachments" in csv_defaults
        else csv_defaults.get("includeAttachments")
    )
    attachment_fields = _attachment_field_names(version_doc)

    def _header_for_question(var_name, label):
        mapped = field_mapping.get(var_name)
        mapped_label = None
        mapped_anonymize = False
        if isinstance(mapped, dict):
            mapped_label = (
                mapped.get("label")
                or mapped.get("alias")
                or mapped.get("header_label")
            )
            mapped_anonymize = bool(mapped.get("anonymize"))
        elif mapped is not None:
            mapped_label = str(mapped)

        if header_mode == "keys":
            return mapped_label or var_name, mapped_anonymize
        return mapped_label or label or var_name, mapped_anonymize

    def _anonymize_value(var_name, value, anonymize_flag=False):
        if value in (None, ""):
            return value
        if (
            anonymization_mode == "none"
            and not anonymize_flag
            and var_name not in anonymized_fields
        ):
            return value
        if anonymization_mode == "remove":
            return empty_field_value
        if anonymization_mode == "hash":
            import hashlib

            return hashlib.sha256(str(value).encode("utf-8")).hexdigest()
        return "[REDACTED]"

    headers = ["response_id", "submitted_by", "submitted_at", "status"]
    field_mapping_rows = []  # List of {var_name, anonymize_flag}

    if version_doc:
        snapshot = version_doc.resolved_snapshot
        sections = snapshot.get("sections", [])
        for section in sections:
            prefix = f"{section.get('title')} - " if len(sections) > 1 else ""
            for question in section.get("questions", []):
                var_name = question.get("variable_name")
                if var_name:
                    header_label, mapped_anonymize = _header_for_question(
                        var_name, question.get("label")
                    )
                    headers.append(f"{prefix}{header_label}" if header_mode != "keys" else header_label)
                    field_mapping_rows.append(
                        {"var_name": var_name, "anonymize": mapped_anonymize}
                    )
    else:
        headers.append("data (raw)")

    # Yield header
    output = io.StringIO()
    writer = csv.writer(output, delimiter=delimiter)
    writer.writerow(headers)
    yield output.getvalue()
    output.truncate(0)
    output.seek(0)

    for r in responses:
        row = [
            str(r.id),
            r.submitted_by,
            _format_export_datetime(r.submitted_at, csv_defaults),
            r.status or "submitted",
        ]
        response_data = _response_data(r)

        if not version_doc:
            row.append(json.dumps(response_data))
        else:
            for mapping in field_mapping_rows:
                var_name = mapping["var_name"]
                val = response_data.get(var_name, "")
                if var_name in attachment_fields and not include_attachments:
                    val = empty_field_value
                if isinstance(val, (list, dict)):
                    val = json.dumps(val)
                row.append(_anonymize_value(var_name, val, mapping["anonymize"]))

        writer.writerow(row)
        yield output.getvalue()
        output.truncate(0)
        output.seek(0)


# -------------------- Export to CSV --------------------
@form_bp.route("/<form_id>/export/csv", methods=["GET"])
@swag_from(
    {
        "tags": ["Form"],
        "responses": {"200": {"description": "Success"}},
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
@limiter.limit(settings.RATE_LIMIT_EXPORT)
def export_responses_csv(form_id):
    app_logger.info(f"Entering export_responses_csv for form_id: {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id
        )

        if not has_form_permission(current_user, form, "view_responses"):
            safe_log_info(
                app_logger,
                "Unauthorized CSV export attempt for form_id: %s by user: %s",
                form_id,
                str(getattr(current_user, "id", "unknown")),
            )
            return error_response(message="Unauthorized to export", status_code=403)

        # Use iterator() for memory efficiency in MongoDB
        responses = (
            FormResponse.objects(
                form=form.id, organization_id=current_user.organization_id
            )
            .no_cache()
            .timeout(False)
        )

        # Apply export limit
        response_count = responses.count()
        if response_count > settings.MAX_EXPORT_RECORDS:
            if settings.REQUIRE_EXPORT_CONSENT:
                # Require user to consent for large exports
                return error_response(
                    message=f"Export would return {response_count} records. Maximum allowed is {settings.MAX_EXPORT_RECORDS}. Please contact admin for larger exports.",
                    status_code=400,
                )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_settings = getattr(form, "data_export_settings", None) or {}
        if hasattr(export_settings, "model_dump"):
            export_settings = export_settings.model_dump(
                exclude_unset=True, exclude_none=True
            )
        csv_defaults = dict(export_settings.get("csv_defaults") or {})

        safe_log_info(
            audit_logger,
            "CSV streaming export initiated for form_id: %s by user: %s",
            form_id,
            str(current_user.id),
        )

        return Response(
            stream_form_csv(form, responses),
            mimetype=f"text/csv; charset={csv_defaults.get('encoding', 'utf-8')}",
            headers={
                "Content-Disposition": f"attachment;filename=form_{form_id}_{timestamp}.csv",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(
            f"Error in export_responses_csv for form_id {form_id}: {str(e)}"
        )
        return error_response(message="Internal server error", status_code=500)


def stream_form_json(form, responses):
    """
    Generates JSON content iteratively for streaming responses.
    """
    anonymization = _anonymization_settings(form)
    export_settings = getattr(form, "data_export_settings", None) or {}
    if hasattr(export_settings, "model_dump"):
        export_settings = export_settings.model_dump(
            exclude_unset=True, exclude_none=True
        )
    csv_defaults = dict(export_settings.get("csv_defaults") or {})
    include_attachments = bool(
        csv_defaults.get("include_attachments")
        if "include_attachments" in csv_defaults
        else csv_defaults.get("includeAttachments")
    )
    attachment_fields = _attachment_field_names(
        getattr(form, "active_version", None)
        or getattr(form, "active_version_doc", None)
        or (form.versions[-1] if getattr(form, "versions", None) else None)
    )
    metadata = {
        "id": str(form.id),
        "title": form.title,
        "slug": form.slug,
        "created_by": form.created_by,
        "created_at": str(form.created_at),
        "status": form.status,
        "is_public": form.is_public,
        "organization_id": form.organization_id,
    }

    yield '{"form_metadata": ' + json.dumps(metadata) + ', "responses": ['

    first = True
    for r in responses:
        if not first:
            yield ","
        payload = r.to_dict() if hasattr(r, "to_dict") else {}
        response_data = _response_data(r)
        if anonymization.get("mode") != "none":
            for field in list(response_data.keys()):
                if field in anonymization["fields"]:
                    response_data[field] = _mask_json_value(
                        response_data.get(field), anonymization["mode"]
                    )
        if not include_attachments:
            for field in list(response_data.keys()):
                if field in attachment_fields:
                    response_data[field] = None
        payload["data"] = response_data
        payload.pop("encrypted_data", None)
        yield json.dumps(payload, default=str)
        first = False

    yield "]}"


@form_bp.route("/<form_id>/export/json", methods=["GET"])
@swag_from(
    {
        "tags": ["Form"],
        "responses": {"200": {"description": "Success"}},
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
@limiter.limit(settings.RATE_LIMIT_EXPORT)
def export_form_with_responses(form_id):
    app_logger.info(f"Entering export_form_with_responses for form_id: {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id
        )

        if not has_form_permission(current_user, form, "view_responses"):
            safe_log_info(
                app_logger,
                "Unauthorized JSON export attempt for form_id: %s by user: %s",
                form_id,
                str(getattr(current_user, "id", "unknown")),
            )
            return error_response(message="Unauthorized", status_code=403)

        responses = (
            FormResponse.objects(
                form=form.id, organization_id=current_user.organization_id
            )
            .no_cache()
            .timeout(False)
        )

        # Apply export limit
        response_count = responses.count()
        if response_count > settings.MAX_EXPORT_RECORDS:
            if settings.REQUIRE_EXPORT_CONSENT:
                # Require user to consent for large exports
                return error_response(
                    message=f"Export would return {response_count} records. Maximum allowed is {settings.MAX_EXPORT_RECORDS}. Please contact admin for larger exports.",
                    status_code=400,
                )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_log_info(
            audit_logger,
            "JSON streaming export initiated for form_id: %s by user: %s",
            form_id,
            str(current_user.id),
        )

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
        safe_log_error(
            app_logger,
            "Error in export_form_with_responses for form_id: %s",
            form_id,
            exc_info=True,
        )
        return error_response(message="Internal server error", status_code=500)


from utils.response_helper import success_response, error_response
