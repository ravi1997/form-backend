from . import form_bp
from flasgger import swag_from
from flask import request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from routes.v1.form import form_bp
from services.response_service import FormResponseService, FormResponseCreateSchema
from routes.v1.form.helper import get_current_user, has_form_permission
from models.Form import Form
from mongoengine import DoesNotExist

response_service = FormResponseService()

@form_bp.route("/<form_id>/responses", methods=["POST"])
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
        },
        {
            "name": "body",
            "in": "body",
            "schema": {
                "$ref": "#/definitions/FormResponseCreateSchema"
            }
        }
    ]
})
@jwt_required()
def submit_response(form_id):
    """
    Authenticated form submission.
    """
    current_user = get_current_user()
    data = request.get_json()
    
    try:
        form = Form.objects.get(id=form_id, is_deleted=False)
        
        # 1. Permission Check
        if not has_form_permission(current_user, form, "submit"):
            return jsonify({"error": "You do not have permission to submit to this form"}), 403
            
        # 2. Validation & Service Call
        # We need to inject form, organization_id and submitted_by into the schema
        submission_data = {
            "form": str(form.id),
            "form_version": str(form.active_version.id) if form.active_version else "1.0.0",
            "organization_id": current_user.organization_id,
            "data": data.get("data", {}),
            "submitted_by": str(current_user.id),
            "ip_address": request.remote_addr,
            "user_agent": request.user_agent.string
        }
        
        if form.project:
            submission_data["project"] = str(form.project.id)
            
        create_schema = FormResponseCreateSchema(**submission_data)
        response = response_service.create_submission(create_schema)
        
        return jsonify({
            "message": "Response submitted successfully",
            "response_id": str(response.id)
        }), 201
        
    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        current_app.logger.error(f"Error submitting response: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 400

@form_bp.route("/<form_id>/responses", methods=["GET"])
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
def list_responses(form_id):
    """
    List responses for a specific form (paginated).
    """
    current_user = get_current_user()
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    
    try:
        form = Form.objects.get(id=form_id, is_deleted=False)
        
        if not has_form_permission(current_user, form, "view_responses"):
            return jsonify({"error": "You do not have permission to view responses for this form"}), 403
            
        result = response_service.list_by_form(
            form_id=str(form.id),
            organization_id=current_user.organization_id,
            page=page,
            page_size=page_size
        )
        
        return jsonify(result.to_dict()), 200
        
    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        current_app.logger.error(f"Error listing responses: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 400
