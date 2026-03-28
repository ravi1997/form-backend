from . import form_bp
from flasgger import swag_from
from datetime import datetime, timezone
from routes.v1.form.helper import get_current_user
from routes.v1.form import form_bp
from flask import current_app, request, jsonify
from flask_jwt_extended import jwt_required
from mongoengine import DoesNotExist
from models import Form, FormResponse
from utils.exceptions import NotFoundError, ValidationError, ForbiddenError, ServiceError
from utils.response_helper import success_response, error_response
import json
from utils.script_engine import execute_safe_script
from logger.unified_logger import app_logger, error_logger, audit_logger


# -------------------- Public Anonymous Submission --------------------
@form_bp.route("/<form_id>/public-submit", methods=["POST"])
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
def submit_public_response(form_id):
    app_logger.info(f"Entering submit_public_response for form {form_id}")
    data = request.get_json()
    try:
        # Public lookup - must be careful but it is allowed for is_public forms
        form = Form.objects.get(id=form_id, is_deleted=False)

        # Check if form is published
        if form.status != "published":
            app_logger.warning(
                f"Attempted public submission to non-published form {form_id} (status: {form.status})"
            )
            return error_response(message=f"Form is {form.status}, not accepting submissions", status_code=403)

        # Check if form has expired
        now = datetime.now(timezone.utc)
        if form.expires_at and now > form.expires_at.replace(tzinfo=timezone.utc):
            app_logger.warning(
                f"Attempted public submission to expired form {form_id} (expired at: {form.expires_at})"
            )
            return error_response(message="Form has expired", status_code=403)

        # Check if form is scheduled for future
        if form.publish_at and now < form.publish_at.replace(tzinfo=timezone.utc):
            app_logger.warning(
                f"Attempted public submission to future scheduled form {form_id} (publish at: {form.publish_at})"
            )
            return error_response(message="Form is not yet available", status_code=403)

        if not form.is_public:
            app_logger.warning(f"Attempted public submission to non-public form {form_id}")
            return error_response(message="Form is not public", status_code=403)

        from services.response_service import FormResponseService, FormResponseCreateSchema
        response_service = FormResponseService()
        
        submission_data = {
            "form": str(form.id),
            "organization_id": form.organization_id,
            "data": data.get("data", {}),
            "submitted_by": "anonymous",
            "ip_address": request.remote_addr,
            "user_agent": request.user_agent.string
        }
        
        create_schema = FormResponseCreateSchema(**submission_data)
        response = response_service.create_submission(create_schema)
        
        audit_logger.info(f"Anonymous response {response.id} submitted for form {form_id}")

        return success_response(
            data={"response_id": str(response.id)},
            message="Response submitted anonymously",
            status_code=201
        )
    except DoesNotExist:
        app_logger.warning(f"Form {form_id} not found for public submission")
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Error in submit_public_response for form {form_id}: {e}")
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<string:form_id>/history", methods=["GET"])
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
def form_submission_history(form_id):
    app_logger.info(f"Entering form_submission_history for form {form_id}")
    current_user = get_current_user()
    try:
        question_id = request.args.get("question_id")
        primary_value = request.args.get("primary_value")

        if not question_id or not primary_value:
            app_logger.warning(f"Missing parameters in form_submission_history for form {form_id}")
            return (
                jsonify(
                    {"error": "Missing 'question_id' or 'primary_value' parameter"}
                ),
                400,
            )

        app_logger.info(
            f"User {current_user.username} is requesting submission history for form {form_id}, question {question_id} with value '{primary_value}'"
        )

        # Enforce tenant isolation
        # Construct the search query directly instead of using test_client anti-pattern
        query = {
            f"data__{question_id}": primary_value,
            "form": form_id,
            "organization_id": current_user.organization_id,
            "is_deleted": False
        }
        
        responses = FormResponse.objects(**query).order_by("submitted_at").limit(100)
        
        result = [
            {"_id": str(r.id), "submitted_at": r.submitted_at.isoformat()} for r in responses
        ]
        
        app_logger.info(f"Successfully retrieved history for form {form_id}, found {len(result)} records")
        return success_response(data=result)

    except Exception as e:
        error_logger.error(
            f"Error fetching form submission history for {form_id}: {str(e)}", exc_info=True
        )
        return error_response(message="Internal server error", status_code=500)


# -------------------- Workflow Next Action Check --------------------
@form_bp.route("/<form_id>/next-action", methods=["GET"])
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
def check_next_action(form_id):
    """
    Check if any active workflows should be triggered for this form.
    """
    app_logger.info(f"--- Entering check_next_action for form_id: {form_id} ---")
    try:
        from models.Workflow import ApprovalWorkflow
        current_user = get_current_user()
        if not current_user:
            app_logger.warning("Unauthorized access in check_next_action")
            return jsonify({"error": "Unauthorized"}), 401

        # Verify form exists
        form = Form.objects(
            id=form_id,
            organization_id=current_user.organization_id,
            is_deleted=False,
        ).first()
        if not form:
            app_logger.warning(
                f"Check Next Action failed: Form {form_id} not found in org {current_user.organization_id}"
            )
            return jsonify({"error": "Form not found"}), 404

        # Get response_id from query params if provided
        response_id = request.args.get("response_id")

        if response_id:
            # Check workflows for a specific response
            response = FormResponse.objects(
                id=response_id,
                form=form.id,
                organization_id=current_user.organization_id,
                is_deleted=False,
            ).first()
            if not response:
                app_logger.warning(
                    f"Check Next Action failed: Response {response_id} not found"
                )
                return jsonify({"error": "Response not found"}), 404

            submitted_data = response.data
        else:
            # No specific response - return available workflows for this form
            workflows = ApprovalWorkflow.objects(
                trigger_form_id=str(form.id), 
                organization_id=current_user.organization_id,
                status="active"
            )

            workflow_list = []
            for wf in workflows:
                workflow_list.append(
                    {
                        "id": str(wf.id),
                        "name": wf.name,
                        "description": wf.description,
                        "steps_count": len(wf.steps)
                    }
                )

            app_logger.info(f"Returned {len(workflow_list)} available workflows for form {form_id}")
            return (
                jsonify(
                    {
                        "form_id": str(form.id),
                        "workflows": workflow_list,
                        "count": len(workflow_list),
                    }
                ),
                200,
            )

        # Evaluate workflows for the specific response
        workflows = ApprovalWorkflow.objects(
            trigger_form_id=str(form.id), 
            organization_id=current_user.organization_id,
            status="active"
        )

        # Simplified: Check if any step needs approval for this response
        # In a real system, this would trigger an ApprovalProcess instance.
        # For this refactor, we just identify if a workflow is applicable.
        triggered_workflows = []
        for wf in workflows:
            triggered_workflows.append({
                "workflow_id": str(wf.id),
                "workflow_name": wf.name,
                "first_step": wf.steps[0].step_name if wf.steps else None
            })

        return success_response(data={
            "form_id": str(form.id),
            "response_id": response_id,
            "triggered_workflows": triggered_workflows
        })

    except Exception as e:
        error_logger.error(f"Error checking next action for {form_id}: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)
