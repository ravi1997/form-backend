from . import form_bp
from flasgger import swag_from
from routes.v1.form import form_bp
from flask import request, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required
from mongoengine import DoesNotExist
from models import Form, FormResponse
from models.User import Role
from utils.security import require_roles

# -------------------- Additional Functional Routes --------------------


@form_bp.route("/slug-available", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Check if a form slug is already taken."
        }
    }
})
@jwt_required()
def check_slug():
    """Check if a form slug is already taken."""
    slug = request.args.get("slug")
    if not slug:
        return jsonify({"error": "slug parameter is required"}), 400
    exists = Form.objects(slug=slug).first() is not None
    return jsonify({"available": not exists}), 200


@form_bp.route("/<form_id>/share", methods=["POST"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Admin only: Grant editor/viewer/submitter permissions for a form."
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": true
        }
    ]
})
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def share_form(form_id):
    """Admin only: Grant editor/viewer/submitter permissions for a form."""
    data = request.get_json(silent=True) or {}
    try:
        form = Form.objects.get(id=form_id)
        form.update(
            add_to_set__editors=data.get("editors", []),
            add_to_set__viewers=data.get("viewers", []),
            add_to_set__submitters=data.get("submitters", []),
        )
        return jsonify({"message": "Permissions updated"}), 200
    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404


@form_bp.route("/<form_id>/archive", methods=["PATCH"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Admin only: Change form status to 'archived'."
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": true
        }
    ]
})
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def archive_form(form_id):
    """Admin only: Change form status to 'archived'."""
    try:
        form = Form.objects.get(id=form_id)
        form.update(set__status="archived")
        return jsonify({"message": "Form archived"}), 200
    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404


@form_bp.route("/<form_id>/restore", methods=["PATCH"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Admin only: Change form status from 'archived' back to 'draft'."
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": true
        }
    ]
})
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def restore_form(form_id):
    """Admin only: Change form status from 'archived' back to 'draft'."""
    try:
        form = Form.objects.get(id=form_id, status="archived")
        form.update(set__status="draft")
        return jsonify({"message": "Form restored"}), 200
    except DoesNotExist:
        return jsonify({"error": "Archived form not found"}), 404


# -------------------- Delete All Responses --------------------
@form_bp.route("/<form_id>/responses", methods=["DELETE"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Admin only: Purge all collected responses for a specific form."
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": true
        }
    ]
})
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def delete_all_responses(form_id):
    """Admin only: Purge all collected responses for a specific form."""
    try:
        form = Form.objects.get(id=form_id)
        deleted_count = FormResponse.objects(form=form.id).delete()
        return jsonify({"message": f"Deleted {deleted_count} responses"}), 200
    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404


# -------------------- Toggle Public Access --------------------
@form_bp.route("/<form_id>/toggle-public", methods=["PATCH"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Admin only: Toggle between private and public access for a form."
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": true
        }
    ]
})
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def toggle_form_public(form_id):
    """Admin only: Toggle between private and public access for a form."""
    try:
        form = Form.objects.get(id=form_id)
        form.is_public = not form.is_public
        form.save()
        return (
            jsonify(
                {"message": "Form public access toggled", "is_public": form.is_public}
            ),
            200,
        )
    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404


# -------------------- Count Responses for Form --------------------
@form_bp.route("/<form_id>/responses/count", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Get total submission count for a form."
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": true
        }
    ]
})
@jwt_required()
def count_responses(form_id):
    """Get total submission count for a form."""
    try:
        form = Form.objects.get(id=form_id)
        count = FormResponse.objects(form=form.id).count()
        return jsonify({"form_id": form_id, "response_count": count}), 200
    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404


# -------------------- Get Last Submission --------------------
@form_bp.route("/<form_id>/responses/last", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Fetch the most recent response record for a form."
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": true
        }
    ]
})
@jwt_required()
def last_response(form_id):
    """Fetch the most recent response record for a form."""
    try:
        form = Form.objects.get(id=form_id)
        response = FormResponse.objects(form=form.id).order_by("-submitted_at").first()
        if response:
            d = response.to_mongo().to_dict()
            d["id"] = str(d.pop("_id"))
            return jsonify(d), 200
        return jsonify({"message": "No responses found"}), 404
    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404


# -------------------- Duplicate Check for Response --------------------
@form_bp.route("/<form_id>/check-duplicate", methods=["POST"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Check if the current user has already submitted this exact data."
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": true
        }
    ]
})
@jwt_required()
def check_duplicate_submission(form_id):
    """Check if the current user has already submitted this exact data."""
    data = request.get_json(silent=True) or {}
    submitted_by = str(get_jwt_identity())
    try:
        form = Form.objects.get(id=form_id)
        exists = FormResponse.objects(
            form=form.id, submitted_by=submitted_by, data=data.get("data")
        ).first()
        return jsonify({"duplicate": exists is not None}), 200
    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404
