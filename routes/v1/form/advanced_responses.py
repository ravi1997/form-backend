from . import form_bp
from flasgger import swag_from
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Form, FormResponse
from routes.v1.form.helper import get_current_user, has_form_permission
from mongoengine import DoesNotExist
from logger.unified_logger import app_logger, error_logger, audit_logger
from utils.mongodb_query_helper import NoSQLInjector
from utils.sensitive_data_redaction import safe_log_info, safe_log_error
from utils.response_helper import success_response, error_response, FormSerializer
from services.form_service import FormService
from services.filter_builder_service import FilterBuilderService
from utils.exceptions import ValidationError as ServiceValidationError

advanced_responses_bp = Blueprint("advanced_responses", __name__)
form_service = FormService()


@advanced_responses_bp.route("/", methods=["GET"])
@swag_from(
    {
        "tags": ["Advanced_Responses"],
        "responses": {"200": {"description": "List forms for the current organization"}},
    }
)
@jwt_required()
def list_forms():
    """
    Compatibility endpoint for the dashboard client.

    The Flutter dashboard expects GET /form/api/v1/forms/, so we expose a
    tenant-scoped listing here that mirrors the newer form listing behavior.
    """
    current_user = get_current_user()
    if not current_user:
        return error_response(message="User not found", status_code=401)

    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 50, type=int)
    is_template = request.args.get("is_template", "false").lower() == "true"

    filters = {
        "organization_id": current_user.organization_id,
        "is_deleted": False,
    }
    if is_template:
        filters["is_template"] = True

    result = form_service.list_paginated(page=page, page_size=page_size, **filters)
    data = result.to_dict()
    data["items"] = [FormSerializer.serialize(item) for item in data.get("items", [])]
    return success_response(data=data)


@advanced_responses_bp.route("/fetch/external", methods=["GET"])
@swag_from(
    {"tags": ["Advanced_Responses"], "responses": {"200": {"description": "Success"}}}
)
@jwt_required()
def fetch_external_form_data():
    """
    Fetch data from another form response where some question may have match for a value.
    Query Params: form_id, question_id, value
    """
    form_id = request.args.get("form_id")
    question_id = request.args.get("question_id")
    value = request.args.get("value")

    app_logger.info(
        f"Fetching external form data: form_id={form_id}, question_id={question_id}, value={value}"
    )

    if not all([form_id, question_id, value]):
        return jsonify({"error": "Missing form_id, question_id or value"}), 400

    try:
        current_user = get_current_user()
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id
        )

        if not has_form_permission(current_user, form, "view"):
            error_logger.warning(
                f"Unauthorized external data fetch attempt by user {current_user.id} for form {form_id}"
            )
            return jsonify({"error": "Unauthorized to view this form"}), 403

        # Search responses for the match
        # FormResponse data is structured like { section_id: { question_id: value } }
        # We need a more flexible query if we don't know the section_id
        # For now, we'll try to find it in any section
        query = {f"data__*__{question_id}": value, "form": form.id, "deleted": False}
        # Note: MongoDB/MongoEngine might need a different syntax for deep nested lookup without section_id
        # Alternatively, find any response where data contains the value for question_id

        # Simplified: iterate through sections if known, or use raw mongo query
        # Sanitize inputs to prevent NoSQL injection
        safe_question_id = NoSQLInjector.sanitize_key(question_id)
        safe_value = NoSQLInjector.escape_value(value)

        # Build safe OR query
        or_conditions = []
        if form.versions:
            latest = form.versions[-1]
            sections = latest.resolved_snapshot.get("sections", []) if hasattr(latest, "resolved_snapshot") else []
            for section in sections:
                section_id_str = NoSQLInjector.sanitize_key(str(section.get("id")))
                or_conditions.append(
                    {f"data.{section_id_str}.{safe_question_id}": safe_value}
                )

        responses = FormResponse.objects(
            __raw__={
                "form": form.id,
                "deleted": False,
                "$or": or_conditions,
            }
        )

        app_logger.info(
            f"Fetched {len(responses)} external responses for form {form_id}"
        )
        return jsonify([r.to_mongo().to_dict() for r in responses]), 200

    except DoesNotExist:
        safe_log_info(
            app_logger, "Form %s not found during external data fetch", form_id
        )
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        safe_log_error(
            app_logger, "Error fetching external form data: %s", str(e), exc_info=True
        )
        return jsonify({"error": str(e)}), 500


@advanced_responses_bp.route("/<form_id>/fetch/same", methods=["GET"])
@swag_from(
    {
        "tags": ["Advanced_Responses"],
        "responses": {"200": {"description": "Success"}},
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
def fetch_same_form_data(form_id):
    """
    Fetch data from same form response where some question may have match for a value.
    Query Params: question_id, value
    """
    question_id = request.args.get("question_id")
    value = request.args.get("value")

    app_logger.info(
        f"Fetching same form data for form {form_id}: question_id={question_id}, value={value}"
    )

    if not all([question_id, value]):
        return jsonify({"error": "Missing question_id or value"}), 400

    try:
        current_user = get_current_user()
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id
        )

        if not has_form_permission(current_user, form, "view"):
            error_logger.warning(
                f"Unauthorized same-form data fetch attempt by user {current_user.id} for form {form_id}"
            )
            return jsonify({"error": "Unauthorized to view this form"}), 403

        responses = FormResponse.objects(
            __raw__={
                "form": form.id,
                "deleted": False,
                "$or": (
                    [
                        {f"data.{section.get('id')}.{question_id}": value}
                        for section in (form.versions[-1].resolved_snapshot.get("sections", []) if form.versions else [])
                    ]
                    if form.versions
                    else []
                ),
            }
        )

        app_logger.info(
            f"Fetched {len(responses)} same-form responses for form {form_id}"
        )
        return jsonify([r.to_mongo().to_dict() for r in responses]), 200

    except DoesNotExist:
        error_logger.warning(f"Form {form_id} not found during same-form data fetch")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(f"Error fetching same-form data: {str(e)}")
        return jsonify({"error": str(e)}), 500


@advanced_responses_bp.route("/<form_id>/responses/questions", methods=["GET"])
@swag_from(
    {
        "tags": ["Advanced_Responses"],
        "responses": {"200": {"description": "Success"}},
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
def fetch_specific_questions(form_id):
    """
    Fetching particular questions responses from a form only.
    Query Params: question_ids (comma separated)
    """
    question_ids_raw = request.args.get("question_ids")
    app_logger.info(
        f"Fetching specific questions for form {form_id}: {question_ids_raw}"
    )

    if not question_ids_raw:
        return jsonify({"error": "Missing question_ids"}), 400

    question_ids = question_ids_raw.split(",")

    try:
        current_user = get_current_user()
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id
        )

        if not has_form_permission(current_user, form, "view"):
            error_logger.warning(
                f"Unauthorized specific question fetch attempt by user {current_user.id} for form {form_id}"
            )
            return jsonify({"error": "Unauthorized"}), 403

        responses = FormResponse.objects(form=form.id, is_deleted=False)

        result = []
        for r in responses:
            extracted = {}
            for section_id, section_data in r.data.items():
                if isinstance(section_data, dict):
                    for qid in question_ids:
                        if qid in section_data:
                            extracted[qid] = section_data[qid]
            result.append(
                {
                    "response_id": str(r.id),
                    "data": extracted,
                    "submitted_at": r.submitted_at,
                }
            )

        app_logger.info(
            f"Extracted questions for {len(result)} responses in form {form_id}"
        )
        return jsonify(result), 200

    except DoesNotExist:
        error_logger.warning(f"Form {form_id} not found during specific question fetch")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(f"Error fetching specific questions: {str(e)}")
        return jsonify({"error": str(e)}), 500


@advanced_responses_bp.route("/<form_id>/responses/meta", methods=["GET"])
@swag_from(
    {
        "tags": ["Advanced_Responses"],
        "responses": {"200": {"description": "Success"}},
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
def fetch_response_meta(form_id):
    """
    Fetching meta information about a form response like number of response etc.
    """
    app_logger.info(f"Fetching response meta for form {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id
        )

        if not has_form_permission(current_user, form, "view"):
            error_logger.warning(
                f"Unauthorized response meta fetch attempt by user {current_user.id} for form {form_id}"
            )
            return jsonify({"error": "Unauthorized"}), 403

        total_responses = FormResponse.objects(form=form.id, is_deleted=False).count()
        draft_responses = FormResponse.objects(
            form=form.id, is_deleted=False, is_draft=True
        ).count()
        submitted_responses = total_responses - draft_responses

        # Last submission
        last_response = (
            FormResponse.objects(form=form.id, is_deleted=False)
            .order_by("-submitted_at")
            .first()
        )

        app_logger.info(f"Response meta fetched for form {form_id}")
        return (
            jsonify(
                {
                    "form_id": form_id,
                    "total_responses": total_responses,
                    "draft_count": draft_responses,
                    "submitted_count": submitted_responses,
                    "last_submission": (
                        last_response.submitted_at if last_response else None
                    ),
                }
            ),
            200,
        )

    except DoesNotExist:
        error_logger.warning(f"Form {form_id} not found during response meta fetch")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(f"Error fetching response meta: {str(e)}")
        return jsonify({"error": str(e)}), 500


@advanced_responses_bp.route("/<form_id>/access-control", methods=["GET"])
@swag_from(
    {
        "tags": ["Advanced_Responses"],
        "responses": {"200": {"description": "Success"}},
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
def get_form_access_control(form_id):
    """
    User access control for a forms.
    Returns a detailed JSON report of the current user's permissions.
    """
    app_logger.info(f"Fetching access control report for form {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id
        )

        # Granular checks
        permissions = {
            "view_form": has_form_permission(current_user, form, "view"),
            "submit_form": has_form_permission(current_user, form, "submit"),
            "edit_design": has_form_permission(current_user, form, "edit_design"),
            "manage_access": has_form_permission(current_user, form, "manage_access"),
            "view_responses": has_form_permission(current_user, form, "view_responses"),
            "edit_responses": has_form_permission(current_user, form, "edit_responses"),
            "delete_responses": has_form_permission(
                current_user, form, "delete_responses"
            ),
            "view_audit": has_form_permission(current_user, form, "view_audit"),
            "delete_form": has_form_permission(current_user, form, "delete_form"),
        }

        # Context details
        policy = form.access_policy if hasattr(form, "access_policy") else None

        app_logger.info(f"Access control report generated for form {form_id}")
        return (
            jsonify(
                {
                    "form_id": form_id,
                    "title": form.title,
                    "current_user": {
                        "id": str(current_user.id),
                        "roles": current_user.roles,
                        "department": getattr(current_user, "department", None),
                    },
                    "is_public": form.is_public,
                    "permissions": permissions,
                    "policy_summary": (
                        {
                            "visibility": (
                                policy.form_visibility if policy else "legacy"
                            ),
                            "response_scope": (
                                policy.response_visibility if policy else "legacy"
                            ),
                            "allowed_departments": (
                                policy.allowed_departments if policy else []
                            ),
                        }
                        if policy
                        else None
                    ),
                }
            ),
            200,
        )

    except DoesNotExist:
        error_logger.warning(f"Form {form_id} not found during access control fetch")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(f"Error fetching access control: {str(e)}")
        return jsonify({"error": str(e)}), 500


@advanced_responses_bp.route("/<form_id>/access-policy", methods=["POST", "PUT"])
@swag_from(
    {
        "tags": ["Advanced_Responses"],
        "responses": {"200": {"description": "Success"}},
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
def update_access_policy(form_id):
    """
    Management route to update the Access Policy for a form.
    Requires 'manage_access' permission.
    """
    app_logger.info(f"Updating access policy for form {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id
        )

        if not has_form_permission(current_user, form, "manage_access"):
            error_logger.warning(
                f"Unauthorized access policy update attempt by user {current_user.id} for form {form_id}"
            )
            return (
                jsonify({"error": "Unauthorized to manage access for this form"}),
                403,
            )

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        pol_data = data.get("access_policy", data)

        # Initialize if missing
        if not form.access_policy:
            from models import AccessPolicy

            form.access_policy = AccessPolicy()

        # Update fields
        fields = [
            "can_view_responses",
            "can_edit_responses",
            "can_delete_responses",
            "response_visibility",
            "can_create_versions",
            "can_edit_design",
            "can_clone_form",
            "can_manage_access",
            "can_view_audit_logs",
            "can_delete_form",
            "form_visibility",
            "allowed_departments",
        ]

        updated_fields = []
        for field in fields:
            if field in pol_data:
                setattr(form.access_policy, field, pol_data[field])
                updated_fields.append(field)

        form.save()
        audit_logger.info(
            f"User {current_user.id} updated access policy for form {form_id}. Updated fields: {updated_fields}"
        )
        return (
            jsonify(
                {
                    "message": "Access policy updated successfully",
                    "policy": form.access_policy.to_mongo().to_dict(),
                }
            ),
            200,
        )

    except DoesNotExist:
        error_logger.warning(f"Form {form_id} not found during access policy update")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(f"Error updating access policy: {str(e)}")
        return jsonify({"error": str(e)}), 400


@advanced_responses_bp.route("/<form_id>/responses/filter", methods=["POST"])
@swag_from(
    {
        "tags": ["Advanced_Responses"],
        "summary": "Filter form responses using structured visual filters",
        "parameters": [
            {
                "name": "form_id",
                "in": "path",
                "type": "string",
                "required": True,
                "description": "ID of the form whose responses to filter",
            },
            {
                "name": "body",
                "in": "body",
                "required": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "filters": {
                            "type": "array",
                            "description": "Array of filter rule objects",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "field": {"type": "string"},
                                    "operator": {"type": "string"},
                                    "value": {},
                                    "field_type": {
                                        "type": "string",
                                        "enum": ["string", "number", "date", "boolean"],
                                    },
                                    "is_meta": {"type": "boolean"},
                                },
                                "required": ["field", "operator", "field_type"],
                            },
                        },
                        "page": {"type": "integer", "default": 1},
                        "page_size": {"type": "integer", "default": 50},
                    },
                },
            },
        ],
        "responses": {
            "200": {"description": "Filtered, paginated response list"},
            "400": {"description": "Invalid filter specification"},
            "401": {"description": "Unauthenticated"},
            "403": {"description": "Forbidden"},
            "404": {"description": "Form not found"},
        },
    }
)
@jwt_required()
def filter_responses(form_id):
    """
    POST /advanced_responses/<form_id>/responses/filter

    Accept a JSON body with a ``filters`` array and return paginated
    FormResponse documents matching all supplied criteria.

    The filter engine guarantees:
    - Every query is scoped to the caller's organisation and the specified form.
    - No MongoDB operator injection is possible via filter input.
    - Unsupported operators or invalid types raise a 400 error.
    """
    app_logger.info(f"Entering filter_responses for form_id: {form_id}")

    current_user = get_current_user()
    if not current_user:
        return error_response(message="User not found", status_code=401)

    body = request.get_json(silent=True) or {}
    raw_filters = body.get("filters", [])
    page = int(body.get("page", 1))
    page_size = int(body.get("page_size", 50))

    # Clamp page_size to a safe maximum
    page_size = max(1, min(page_size, 200))
    page = max(1, page)

    try:
        # ── Resolve form and check permission ────────────────────────────
        from models import Form
        from mongoengine import DoesNotExist as _DoesNotExist
        from uuid import UUID

        try:
            form_uuid = UUID(str(form_id))
        except ValueError:
            return error_response(message="Invalid form ID format", status_code=400)

        try:
            form = Form.objects.get(
                id=form_uuid,
                organization_id=current_user.organization_id,
                is_deleted=False,
            )
        except _DoesNotExist:
            return error_response(message="Form not found", status_code=404)

        if not has_form_permission(current_user, form, "view_responses"):
            error_logger.warning(
                f"User {current_user.id} lacks view_responses on form {form_id}"
            )
            return error_response(
                message="You do not have permission to view responses for this form",
                status_code=403,
            )

        # ── Build safe MongoDB query ──────────────────────────────────────
        mongo_query = FilterBuilderService.build_mongo_query(
            filters=raw_filters,
            organization_id=current_user.organization_id,
            form_id=str(form.id),
        )

        # ── Execute query ─────────────────────────────────────────────────
        from models.Response import FormResponse

        qs = FormResponse.objects(__raw__=mongo_query)
        total = qs.count()
        items = (
            qs.order_by("-submitted_at")
            .skip((page - 1) * page_size)
            .limit(page_size)
        )

        payload = [r.to_mongo().to_dict() for r in items]
        # Stringify ObjectId / UUID values for JSON serialisation
        import json
        from bson import json_util

        payload_clean = json.loads(json_util.dumps(payload))

        result = {
            "items": payload_clean,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "has_next": (page * page_size) < total,
            "has_prev": page > 1,
            "filter_count": len(raw_filters),
        }

        audit_logger.info(
            f"User {current_user.id} applied {len(raw_filters)} filter(s) to form {form_id}; "
            f"matched {total} response(s).",
            extra={
                "user_id": str(current_user.id),
                "form_id": form_id,
                "organization_id": current_user.organization_id,
                "action": "filter_responses",
                "filter_count": len(raw_filters),
                "total_matched": total,
            },
        )

        app_logger.info(
            f"Exiting filter_responses for form_id: {form_id}, "
            f"matched {total} of total responses"
        )
        return success_response(data=result)

    except ServiceValidationError as exc:
        error_logger.error(
            f"Validation error in filter_responses for form {form_id}: {exc}",
            exc_info=True,
        )
        return error_response(
            message=str(exc),
            details=exc.details if hasattr(exc, "details") else {},
            status_code=400,
        )
    except Exception as exc:
        error_logger.error(
            f"Unexpected error in filter_responses for form {form_id}: {exc}",
            exc_info=True,
        )
        return error_response(message=str(exc), status_code=500)
