from . import form_bp
from flasgger import swag_from
from flask import request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from routes.v1.form import form_bp
from services.response_service import FormResponseService, FormResponseCreateSchema
from routes.v1.form.helper import get_current_user, has_form_permission
from models.Form import Form, FormVersion
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
    app_logger.info(f"Entering submit_response for form_id: {form_id}")
    current_user = get_current_user()
    data = request.get_json()
    
    try:
        from uuid import UUID
        try:
            form_uuid = UUID(form_id)
        except ValueError:
            app_logger.warning(f"Invalid form ID format: {form_id}")
            return jsonify({"error": "Invalid form ID format"}), 400

        form = Form.objects.get(
            id=form_uuid,
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        
        # 1. Permission Check
        if not has_form_permission(current_user, form, "submit"):
            app_logger.warning(f"User {current_user.id} does not have permission to submit to form {form_id}")
            return jsonify({"error": "You do not have permission to submit to this form"}), 403
            
        # 2. Validation & Service Call
        # We need to inject form, organization_id and submitted_by into the schema
        active_form_version = None
        if form.active_version_id:
            active_form_version_raw = FormVersion._get_collection().find_one(
                {
                    "form": str(form.id),
                    "version": str(form.active_version_id),
                }
            )
            if active_form_version_raw:
                active_form_version = FormVersion.objects(
                    id=active_form_version_raw["_id"]
                ).first()

        submission_data = {
            "form": str(form.id),
            "form_version": str(active_form_version.id) if active_form_version else "",
            "organization_id": current_user.organization_id,
            "data": data.get("data", {}),
            "submitted_by": str(current_user.id),
            "ip_address": request.remote_addr,
            "user_agent": request.user_agent.string
        }
        
        form_project = getattr(form, "project", None)
        if form_project:
            submission_data["project"] = str(form_project.id)
            
        create_schema = FormResponseCreateSchema(**submission_data)
        response = response_service.create_submission(create_schema)
        
        audit_logger.info(f"User {current_user.id} submitted response {response.id} to form {form_id}", extra={
            "user_id": str(current_user.id),
            "form_id": form_id,
            "response_id": str(response.id),
            "organization_id": current_user.organization_id,
            "action": "submit_response"
        })

        app_logger.info(f"Exiting submit_response for form_id: {form_id}, response_id: {response.id}")
        return jsonify({
            "message": "Response submitted successfully",
            "response_id": str(response.id)
        }), 201
        
    except DoesNotExist:
        app_logger.warning(f"Form not found: {form_id}")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(f"Error submitting response to form {form_id}: {str(e)}", exc_info=True)
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
    app_logger.info(f"Entering list_responses for form_id: {form_id}")
    current_user = get_current_user()
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    
    try:
        form = Form.objects.get(
            id=form_id,
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        
        if not has_form_permission(current_user, form, "view_responses"):
            app_logger.warning(f"User {current_user.id} does not have permission to view responses for form {form_id}")
            return jsonify({"error": "You do not have permission to view responses for this form"}), 403
            
        result = response_service.list_by_form(
            form_id=str(form.id),
            organization_id=current_user.organization_id,
            page=page,
            page_size=page_size
        )
        
        app_logger.info(f"Exiting list_responses for form_id: {form_id}, count: {len(result.items)}")
        return jsonify({
            "success": True,
            "data": result.to_dict()
        }), 200
        
    except DoesNotExist:
        app_logger.warning(f"Form not found: {form_id}")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(f"Error listing responses for form {form_id}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 400
