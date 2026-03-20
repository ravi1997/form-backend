from . import form_bp
from flasgger import swag_from
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from models import Form, FormResponse
from routes.v1.form.helper import get_current_user, has_form_permission
from mongoengine import DoesNotExist

advanced_responses_bp = Blueprint("advanced_responses", __name__)


@advanced_responses_bp.route("/fetch/external", methods=["GET"])
@swag_from({
    "tags": [
        "Advanced_Responses"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@jwt_required()
def fetch_external_form_data():
    """
    Fetch data from another form response where some question may have match for a value.
    Query Params: form_id, question_id, value
    """
    form_id = request.args.get("form_id")
    question_id = request.args.get("question_id")
    value = request.args.get("value")

    if not all([form_id, question_id, value]):
        return jsonify({"error": "Missing form_id, question_id or value"}), 400

    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)

        if not has_form_permission(current_user, form, "view"):
            return jsonify({"error": "Unauthorized to view this form"}), 403

        # Search responses for the match
        # FormResponse data is structured like { section_id: { question_id: value } }
        # We need a more flexible query if we don't know the section_id
        # For now, we'll try to find it in any section
        query = {f"data__*__{question_id}": value, "form": form.id, "deleted": False}
        # Note: MongoDB/MongoEngine might need a different syntax for deep nested lookup without section_id
        # Alternatively, find any response where data contains the value for question_id

        # Simplified: iterate through sections if known, or use raw mongo query
        responses = FormResponse.objects(
            __raw__={
                "form": form.id,
                "deleted": False,
                "$or": (
                    [
                        {f"data.{section.id}.{question_id}": value}
                        for section in form.versions[-1].sections
                    ]
                    if form.versions
                    else []
                ),
            }
        )

        return jsonify([r.to_mongo().to_dict() for r in responses]), 200

    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@advanced_responses_bp.route("/<form_id>/fetch/same", methods=["GET"])
@swag_from({
    "tags": [
        "Advanced_Responses"
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
def fetch_same_form_data(form_id):
    """
    Fetch data from same form response where some question may have match for a value.
    Query Params: question_id, value
    """
    question_id = request.args.get("question_id")
    value = request.args.get("value")

    if not all([question_id, value]):
        return jsonify({"error": "Missing question_id or value"}), 400

    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)

        if not has_form_permission(current_user, form, "view"):
            return jsonify({"error": "Unauthorized to view this form"}), 403

        responses = FormResponse.objects(
            __raw__={
                "form": form.id,
                "deleted": False,
                "$or": (
                    [
                        {f"data.{section.id}.{question_id}": value}
                        for section in form.versions[-1].sections
                    ]
                    if form.versions
                    else []
                ),
            }
        )

        return jsonify([r.to_mongo().to_dict() for r in responses]), 200

    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@advanced_responses_bp.route("/<form_id>/responses/questions", methods=["GET"])
@swag_from({
    "tags": [
        "Advanced_Responses"
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
def fetch_specific_questions(form_id):
    """
    Fetching particular questions responses from a form only.
    Query Params: question_ids (comma separated)
    """
    question_ids_raw = request.args.get("question_ids")
    if not question_ids_raw:
        return jsonify({"error": "Missing question_ids"}), 400

    question_ids = question_ids_raw.split(",")

    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)

        if not has_form_permission(current_user, form, "view"):
            return jsonify({"error": "Unauthorized"}), 403

        responses = FormResponse.objects(form=form.id, deleted=False)

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

        return jsonify(result), 200

    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@advanced_responses_bp.route("/<form_id>/responses/meta", methods=["GET"])
@swag_from({
    "tags": [
        "Advanced_Responses"
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
def fetch_response_meta(form_id):
    """
    Fetching meta information about a form response like number of response etc.
    """
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)

        if not has_form_permission(current_user, form, "view"):
            return jsonify({"error": "Unauthorized"}), 403

        total_responses = FormResponse.objects(form=form.id, deleted=False).count()
        draft_responses = FormResponse.objects(
            form=form.id, deleted=False, is_draft=True
        ).count()
        submitted_responses = total_responses - draft_responses

        # Last submission
        last_response = (
            FormResponse.objects(form=form.id, deleted=False)
            .order_by("-submitted_at")
            .first()
        )

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
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@advanced_responses_bp.route("/micro-info", methods=["GET"])
@swag_from({
    "tags": [
        "Advanced_Responses"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@jwt_required()
def micro_info():
    """
    Route for micro informations (Placeholder).
    """
    return jsonify({"message": "Micro information retrieved", "data": {}}), 200


@advanced_responses_bp.route("/<form_id>/access-control", methods=["GET"])
@swag_from({
    "tags": [
        "Advanced_Responses"
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
def get_form_access_control(form_id):
    """
    User access control for a forms.
    Returns a detailed JSON report of the current user's permissions.
    """
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)

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
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@advanced_responses_bp.route("/<form_id>/access-policy", methods=["POST", "PUT"])
@swag_from({
    "tags": [
        "Advanced_Responses"
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
def update_access_policy(form_id):
    """
    Management route to update the Access Policy for a form.
    Requires 'manage_access' permission.
    """
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)

        if not has_form_permission(current_user, form, "manage_access"):
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

        for field in fields:
            if field in pol_data:
                setattr(form.access_policy, field, pol_data[field])

        form.save()
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
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400
