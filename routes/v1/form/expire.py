from . import form_bp
from flasgger import swag_from
from datetime import datetime, timezone
from flask import request, jsonify
from flask_jwt_extended import jwt_required
from mongoengine import DoesNotExist
from models import Form
from models.User import Role
from routes.v1.form import form_bp
from utils.security import require_roles

# -------------------- Schedule Form Expiration --------------------
@form_bp.route("/<form_id>/expire", methods=["PATCH"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Admin only: Set a date when the form automatically becomes unavailable."
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
def set_form_expiration(form_id):
    """Admin only: Set a date when the form automatically becomes unavailable."""
    data = request.get_json(silent=True) or {}
    try:
        form = Form.objects.get(id=form_id)
        expiration_date = data.get("expires_at")
        if not expiration_date:
            return jsonify({"error": "Expiration date is required"}), 400

        # Convert string to aware datetime
        try:
            exp_dt = datetime.fromisoformat(expiration_date.replace("Z", "+00:00"))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            form.update(set__expires_at=exp_dt)
        except ValueError:
            return jsonify({"error": "Invalid date format, use ISO 8601"}), 400
        return jsonify({"message": f"Form expiration updated to {exp_dt.isoformat()}"}), 200
    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@form_bp.route("/expired", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Admin only: List all forms that have passed their expiration date."
        }
    }
})
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def list_expired_forms():
    """Admin only: List all forms that have passed their expiration date."""
    now = datetime.now(timezone.utc)
    expired_forms = Form.objects(expires_at__lt=now)
    result = []
    for f in expired_forms:
        d = f.to_mongo().to_dict()
        d["id"] = str(d.pop("_id"))
        result.append(d)
    return jsonify(result), 200
