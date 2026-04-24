from flask import Blueprint, request, jsonify
from flasgger import swag_from
from flask_jwt_extended import get_jwt_identity, jwt_required
from models import Form, ApprovalWorkflow, WorkflowStep
from utils.response_helper import success_response, error_response
from utils.security_helpers import get_current_user
from logger.unified_logger import app_logger, error_logger, audit_logger

workflow_bp = Blueprint("workflow", __name__)


def _frontend_step_to_backend(step_data):
    """Translate the frontend workflow step shape into the backend approval step shape."""
    step_name = step_data.get("name") or step_data.get("step_name") or "Step"
    step_type = step_data.get("type")
    config = step_data.get("config") or {}
    approval_type = step_data.get("approval_type")
    if not approval_type:
        if step_type == "parallel":
            approval_type = "parallel"
        else:
            approval_type = "any_one"

    return WorkflowStep(
        step_name=step_name,
        order=step_data.get("order", 1),
        approvers=step_data.get("approvers", []),
        approver_groups=step_data.get("approver_groups", []),
        approval_type=approval_type,
        min_approvals_required=step_data.get(
            "min_approvals_required",
            config.get("min_approvals_required", 1),
        ),
        on_approve_script=config.get("on_approve_script") or step_data.get("on_approve_script"),
        on_reject_script=config.get("on_reject_script") or step_data.get("on_reject_script"),
    )


def _serialize_workflow(workflow):
    return {
        "id": str(workflow.id),
        "name": workflow.name,
        "description": workflow.description,
        "formId": getattr(workflow, "trigger_form_id", None),
        "status": workflow.status,
        "version": 1,
        "steps": [
            {
                "id": str(idx + 1),
                "name": step.step_name,
                "description": None,
                "type": "approval",
                "order": step.order,
                "config": {
                    "approval_type": step.approval_type,
                    "min_approvals_required": step.min_approvals_required,
                    "on_approve_script": getattr(step, "on_approve_script", None),
                    "on_reject_script": getattr(step, "on_reject_script", None),
                },
                "assigneeId": None,
                "dueInDays": None,
                "allowedActions": None,
                "requiresManualAction": True,
                "skippable": False,
                "onCompleteHooks": None,
            }
            for idx, step in enumerate(workflow.steps or [])
        ],
        "transitions": [],
        "createdAt": workflow.created_at.isoformat() if getattr(workflow, "created_at", None) else None,
        "updatedAt": workflow.updated_at.isoformat() if getattr(workflow, "updated_at", None) else None,
        "createdBy": workflow.created_by,
        "initialStepId": None,
        "finalStepIds": [],
        "metadata": workflow.meta_data if hasattr(workflow, "meta_data") else {},
    }

# Verify if models are loaded
HAS_WORKFLOW_MODEL = True
try:
    # Just a sanity check
    _ = ApprovalWorkflow
    _ = WorkflowStep
except NameError:
    HAS_WORKFLOW_MODEL = False
    error_logger.warning("Workflow models not found. Workflow routes will return 501.")


def _no_model():
    return error_response("Workflow feature not available", status_code=501)


@workflow_bp.route("/", methods=["POST"])
@swag_from({
    "tags": [
        "Workflow"
    ],
    "responses": {
        "200": {
            "description": "Create a new multi-step approval workflow."
        }
    }
})
@jwt_required()
def create_workflow():
    """Create a new multi-step approval workflow."""
    app_logger.info("Entering create_workflow")
    if not HAS_WORKFLOW_MODEL:
        app_logger.warning("create_workflow failed: workflow models not available")
        return _no_model()
        
    data = request.get_json(silent=True) or {}
    current_user = get_current_user()
    
    try:
        required_fields = ["name", "steps"]
        for field in required_fields:
            if field not in data:
                app_logger.warning(f"create_workflow failed: missing field {field}")
                return error_response(f"Missing required field: {field}", status_code=400)

        from uuid import UUID
        trigger_form_value = data.get("trigger_form_id") or data.get("formId")
        if not trigger_form_value:
            return error_response("Missing required field: trigger_form_id", status_code=400)
        try:
            trigger_form_uuid = UUID(trigger_form_value)
        except ValueError:
            app_logger.warning(f"create_workflow failed: invalid trigger_form_id format: {trigger_form_value}")
            return error_response("Invalid trigger_form_id format", status_code=400)

        # Validate trigger form exists
        trigger_form = Form.objects(id=trigger_form_uuid, organization_id=current_user.organization_id).first()
        if not trigger_form:
            app_logger.warning(f"create_workflow failed: trigger form {trigger_form_uuid} not found for org {current_user.organization_id}")
            return error_response("Trigger form not found or access denied", status_code=404)

        steps = [_frontend_step_to_backend(s_data) for s_data in data["steps"]]

        workflow = ApprovalWorkflow(
            name=data["name"],
            description=data.get("description"),
            organization_id=current_user.organization_id,
            trigger_form_id=str(trigger_form_uuid),
            status=data.get("status", "active"),
            steps=steps,
            created_by=str(current_user.id),
            is_template=data.get("is_template", False)
        )
        workflow.save()
        
        audit_logger.info(f"Workflow created. ID: {workflow.id}, Name: {workflow.name}, Org: {current_user.organization_id}, User: {current_user.id}")
        app_logger.info(f"Exiting create_workflow successfully. Workflow ID: {workflow.id}")
        return success_response(
            data=_serialize_workflow(workflow),
            message="Approval workflow created successfully",
            status_code=201
        )

    except Exception as e:
        error_logger.error(f"Create Workflow error: {str(e)}", exc_info=True)
        return error_response(str(e), status_code=500)


@workflow_bp.route("/", methods=["GET"])
@swag_from({
    "tags": [
        "Workflow"
    ],
    "responses": {
        "200": {
            "description": "List all workflows for the current organization."
        }
    }
})
@jwt_required()
def list_workflows():
    """List all workflows for the current organization."""
    app_logger.info("Entering list_workflows")
    if not HAS_WORKFLOW_MODEL:
        app_logger.warning("list_workflows failed: workflow models not available")
        return _no_model()
        
    current_user = get_current_user()
    try:
        trigger_form_id = request.args.get("trigger_form_id")
        filters = {"organization_id": current_user.organization_id, "is_deleted": False}
        
        if trigger_form_id:
            filters["trigger_form_id"] = trigger_form_id

        workflows = ApprovalWorkflow.objects(**filters)
        
        result = [_serialize_workflow(w) for w in workflows]

        app_logger.info(f"Exiting list_workflows successfully. Found {len(result)} workflows.")
        return success_response(data={"items": result, "total": len(result)})
    except Exception as e:
        error_logger.error(f"List Workflows error: {str(e)}", exc_info=True)
        return error_response(str(e), status_code=500)


@workflow_bp.route("/<workflow_id>", methods=["GET"])
@swag_from({
    "tags": [
        "Workflow"
    ],
    "responses": {
        "200": {
            "description": "Get detailed workflow definition."
        }
    },
    "parameters": [
        {
            "name": "workflow_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def get_workflow(workflow_id):
    """Get detailed workflow definition."""
    app_logger.info(f"Entering get_workflow for workflow_id: {workflow_id}")
    if not HAS_WORKFLOW_MODEL:
        app_logger.warning(f"get_workflow failed for {workflow_id}: workflow models not available")
        return _no_model()
        
    from uuid import UUID
    current_user = get_current_user()
    try:
        try:
            workflow_uuid = UUID(workflow_id)
        except ValueError:
             app_logger.warning(f"get_workflow failed: invalid workflow_id format: {workflow_id}")
             return error_response("Invalid workflow_id format", status_code=400)

        workflow = ApprovalWorkflow.objects(
            id=workflow_uuid, 
            organization_id=current_user.organization_id,
            is_deleted=False
        ).first()
        
        if not workflow:
            app_logger.warning(f"get_workflow failed: workflow {workflow_uuid} not found for org {current_user.organization_id}")
            return error_response("Workflow not found", status_code=404)

        app_logger.info(f"Exiting get_workflow successfully for workflow_id: {workflow_id}")
        return success_response(data=_serialize_workflow(workflow))
    except Exception as e:
        error_logger.error(f"Get Workflow error: {str(e)}", exc_info=True)
        return error_response(str(e), status_code=500)


@workflow_bp.route("/pending", methods=["GET"])
@jwt_required()
def list_pending_approvals():
    """List workflows with pending approvals for current user."""
    app_logger.info("Entering list_pending_approvals")
    app_logger.info("Exiting list_pending_approvals (placeholder)")
    return success_response(data={"items": [], "total": 0})


@workflow_bp.route("/<workflow_id>", methods=["PUT"])
@swag_from({
    "tags": [
        "Workflow"
    ],
    "responses": {
        "200": {
            "description": "Update an existing workflow."
        }
    },
    "parameters": [
        {
            "name": "workflow_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def update_workflow(workflow_id):
    """Update an existing workflow."""
    app_logger.info(f"Entering update_workflow for workflow_id: {workflow_id}")
    if not HAS_WORKFLOW_MODEL:
        app_logger.warning(f"update_workflow failed for {workflow_id}: workflow models not available")
        return _no_model()
        
    from uuid import UUID
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    
    try:
        try:
            workflow_uuid = UUID(workflow_id)
        except ValueError:
             app_logger.warning(f"update_workflow failed: invalid workflow_id format: {workflow_id}")
             return error_response("Invalid workflow_id format", status_code=400)

        workflow = ApprovalWorkflow.objects(
            id=workflow_uuid, 
            organization_id=current_user.organization_id,
            is_deleted=False
        ).first()
        
        if not workflow:
            app_logger.warning(f"update_workflow failed: workflow {workflow_uuid} not found for org {current_user.organization_id}")
            return error_response("Workflow not found", status_code=404)

        if "name" in data:
            workflow.name = data["name"]
        if "description" in data:
            workflow.description = data["description"]
        if "status" in data:
            workflow.status = data["status"]
        if "steps" in data:
            workflow.steps = [_frontend_step_to_backend(s_data) for s_data in data["steps"]]

        workflow.save()
        audit_logger.info(f"Workflow updated. ID: {workflow.id}, Name: {workflow.name}, Org: {current_user.organization_id}, User: {current_user.id}")
        app_logger.info(f"Exiting update_workflow successfully for workflow_id: {workflow_id}")
        return success_response(data=_serialize_workflow(workflow), message="Workflow updated successfully")
    except Exception as e:
        error_logger.error(f"Update Workflow error: {str(e)}", exc_info=True)
        return error_response(str(e), status_code=500)


@workflow_bp.route("/<workflow_id>", methods=["DELETE"])
@swag_from({
    "tags": [
        "Workflow"
    ],
    "responses": {
        "200": {
            "description": "Soft-delete a workflow."
        }
    },
    "parameters": [
        {
            "name": "workflow_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def delete_workflow(workflow_id):
    """Soft-delete a workflow."""
    app_logger.info(f"Entering delete_workflow for workflow_id: {workflow_id}")
    if not HAS_WORKFLOW_MODEL:
        app_logger.warning(f"delete_workflow failed for {workflow_id}: workflow models not available")
        return _no_model()
        
    from uuid import UUID
    current_user = get_current_user()
    try:
        try:
            workflow_uuid = UUID(workflow_id)
        except ValueError:
             app_logger.warning(f"delete_workflow failed: invalid workflow_id format: {workflow_id}")
             return error_response("Invalid workflow_id format", status_code=400)

        workflow = ApprovalWorkflow.objects(
            id=workflow_uuid, 
            organization_id=current_user.organization_id,
            is_deleted=False
        ).first()
        
        if not workflow:
            app_logger.warning(f"delete_workflow failed: workflow {workflow_uuid} not found for org {current_user.organization_id}")
            return error_response("Workflow not found", status_code=404)

        workflow.soft_delete()
        audit_logger.info(f"Workflow soft-deleted. ID: {workflow_uuid}, Org: {current_user.organization_id}, User: {current_user.id}")
        app_logger.info(f"Exiting delete_workflow successfully for workflow_id: {workflow_id}")
        return success_response(message="Workflow deleted successfully")
    except Exception as e:
        error_logger.error(f"Delete Workflow error: {str(e)}", exc_info=True)
        return error_response(str(e), status_code=500)


@workflow_bp.route("/forms/<form_id>/workflows", methods=["GET"])
@jwt_required()
def list_form_workflows(form_id):
    current_user = get_current_user()
    workflows = ApprovalWorkflow.objects(
        organization_id=current_user.organization_id,
        trigger_form_id=form_id,
        is_deleted=False,
    )
    return success_response(data=[_serialize_workflow(w) for w in workflows])


@workflow_bp.route("/forms/<form_id>/workflows", methods=["POST"])
@jwt_required()
def create_form_workflow(form_id):
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    data["trigger_form_id"] = form_id
    if "steps" not in data:
        return error_response("Missing required field: steps", status_code=400)
    if not HAS_WORKFLOW_MODEL:
        return _no_model()

    from uuid import UUID
    try:
        trigger_form_uuid = UUID(form_id)
    except ValueError:
        return error_response("Invalid trigger_form_id format", status_code=400)

    trigger_form = Form.objects(id=trigger_form_uuid, organization_id=current_user.organization_id).first()
    if not trigger_form:
        return error_response("Trigger form not found or access denied", status_code=404)

    steps = [_frontend_step_to_backend(s_data) for s_data in data["steps"]]
    workflow = ApprovalWorkflow(
        name=data.get("name", "Untitled Workflow"),
        description=data.get("description"),
        organization_id=current_user.organization_id,
        trigger_form_id=str(trigger_form_uuid),
        status=data.get("status", "active"),
        steps=steps,
        created_by=str(current_user.id),
        is_template=data.get("is_template", False),
    )
    workflow.save()
    audit_logger.info(
        f"Workflow created. ID: {workflow.id}, Name: {workflow.name}, Org: {current_user.organization_id}, User: {current_user.id}"
    )
    return success_response(data=_serialize_workflow(workflow), message="Approval workflow created successfully", status_code=201)
