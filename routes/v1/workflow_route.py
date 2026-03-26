from flask import Blueprint, request, jsonify
from flasgger import swag_from
from flask_jwt_extended import get_jwt_identity, jwt_required
from models import Form, ApprovalWorkflow, WorkflowStep
from utils.response_helper import success_response, error_response
from utils.security_helpers import get_current_user
from logger.unified_logger import app_logger, error_logger, audit_logger

workflow_bp = Blueprint("workflow", __name__)

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
        required_fields = ["name", "trigger_form_id", "steps"]
        for field in required_fields:
            if field not in data:
                app_logger.warning(f"create_workflow failed: missing field {field}")
                return error_response(f"Missing required field: {field}", status_code=400)

        from uuid import UUID
        try:
            trigger_form_uuid = UUID(data["trigger_form_id"])
        except ValueError:
            app_logger.warning(f"create_workflow failed: invalid trigger_form_id format: {data['trigger_form_id']}")
            return error_response("Invalid trigger_form_id format", status_code=400)

        # Validate trigger form exists
        trigger_form = Form.objects(id=trigger_form_uuid, organization_id=current_user.organization_id).first()
        if not trigger_form:
            app_logger.warning(f"create_workflow failed: trigger form {trigger_form_uuid} not found for org {current_user.organization_id}")
            return error_response("Trigger form not found or access denied", status_code=404)

        # Build Steps
        steps = []
        for s_data in data["steps"]:
            step = WorkflowStep(
                step_name=s_data.get("step_name"),
                order=s_data.get("order"),
                concurrency_type=s_data.get("concurrency_type", "serial"),
                approvers=s_data.get("approvers", []),
                approver_groups=s_data.get("approver_groups", []),
                required_approvals=s_data.get("required_approvals", 1),
                timeout_hours=s_data.get("timeout_hours", 0),
                escalation_action=s_data.get("escalation_action", "notify_admin"),
                actions=s_data.get("actions", [])
            )
            steps.append(step)

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
            data={"id": str(workflow.id)},
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
        
        result = []
        for w in workflows:
            result.append({
                "id": str(w.id),
                "name": w.name,
                "status": w.status,
                "trigger_form_id": w.trigger_form_id,
                "step_count": len(w.steps),
                "created_at": w.created_at.isoformat() if hasattr(w, 'created_at') and w.created_at else None
            })

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

        steps_data = []
        for s in workflow.steps:
            steps_data.append({
                "step_name": s.step_name,
                "order": s.order,
                "concurrency_type": s.concurrency_type,
                "approvers": s.approvers,
                "approver_groups": s.approver_groups,
                "required_approvals": s.required_approvals,
                "timeout_hours": s.timeout_hours,
                "escalation_action": s.escalation_action,
                "actions": s.actions
            })

        app_logger.info(f"Exiting get_workflow successfully for workflow_id: {workflow_id}")
        return success_response(data={
            "id": str(workflow.id),
            "name": workflow.name,
            "description": workflow.description,
            "trigger_form_id": workflow.trigger_form_id,
            "status": workflow.status,
            "steps": steps_data,
            "is_template": workflow.is_template,
            "created_by": workflow.created_by
        })
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
            # Rebuild steps
            steps = []
            for s_data in data["steps"]:
                step = WorkflowStep(
                    step_name=s_data.get("step_name"),
                    order=s_data.get("order"),
                    concurrency_type=s_data.get("concurrency_type", "serial"),
                    approvers=s_data.get("approvers", []),
                    approver_groups=s_data.get("approver_groups", []),
                    required_approvals=s_data.get("required_approvals", 1),
                    timeout_hours=s_data.get("timeout_hours", 0),
                    escalation_action=s_data.get("escalation_action", "notify_admin"),
                    actions=s_data.get("actions", [])
                )
                steps.append(step)
            workflow.steps = steps

        workflow.save()
        audit_logger.info(f"Workflow updated. ID: {workflow.id}, Name: {workflow.name}, Org: {current_user.organization_id}, User: {current_user.id}")
        app_logger.info(f"Exiting update_workflow successfully for workflow_id: {workflow_id}")
        return success_response(message="Workflow updated successfully")
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

