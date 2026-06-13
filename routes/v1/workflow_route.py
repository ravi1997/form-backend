from uuid import UUID

from flask import Blueprint, request
from flasgger import swag_from
from flask_jwt_extended import jwt_required
from models import Form, ApprovalWorkflow, WorkflowStep
from utils.response_helper import success_response, error_response
from utils.security_helpers import get_current_user
from logger.unified_logger import app_logger, audit_logger

workflow_bp = Blueprint("workflow", __name__)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _frontend_step_to_backend(step_data):
    """Translate the frontend workflow step shape into the backend approval step shape."""
    step_name = step_data.get("name") or step_data.get("step_name") or "Step"
    step_type = step_data.get("type")
    config = step_data.get("config") or {}
    approval_type = step_data.get("approval_type")
    if not approval_type:
        approval_type = "parallel" if step_type == "parallel" else "any_one"

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
        on_approve_script=config.get("on_approve_script")
        or step_data.get("on_approve_script"),
        on_reject_script=config.get("on_reject_script")
        or step_data.get("on_reject_script"),
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
        "createdAt": (
            workflow.created_at.isoformat()
            if getattr(workflow, "created_at", None)
            else None
        ),
        "updatedAt": (
            workflow.updated_at.isoformat()
            if getattr(workflow, "updated_at", None)
            else None
        ),
        "createdBy": workflow.created_by,
        "initialStepId": None,
        "finalStepIds": [],
        "metadata": workflow.meta_data if hasattr(workflow, "meta_data") else {},
    }


def _parse_uuid(value, label="id"):
    """Parse a UUID string, returning (uuid, error_response) tuple."""
    try:
        return UUID(value), None
    except ValueError:
        app_logger.warning(f"Invalid {label} format: {value}")
        return None, error_response(f"Invalid {label} format", status_code=400)


# ── Routes ───────────────────────────────────────────────────────────────────


@workflow_bp.route("/", methods=["POST"])
@swag_from(
    {
        "tags": ["Workflow"],
        "responses": {
            "200": {"description": "Create a new multi-step approval workflow."}
        },
    }
)
@jwt_required()
def create_workflow():
    """Create a new multi-step approval workflow."""
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}

    for field in ["name", "steps"]:
        if field not in data:
            app_logger.warning(f"create_workflow failed: missing field {field}")
            return error_response(f"Missing required field: {field}", status_code=400)

    trigger_form_value = data.get("trigger_form_id") or data.get("formId")
    if not trigger_form_value:
        return error_response(
            "Missing required field: trigger_form_id", status_code=400
        )

    trigger_form_uuid, err = _parse_uuid(trigger_form_value, "trigger_form_id")
    if err:
        return err

    trigger_form = Form.objects(
        id=trigger_form_uuid, organization_id=current_user.organization_id
    ).first()
    if not trigger_form:
        app_logger.warning(
            f"create_workflow: trigger form {trigger_form_uuid} not found for org {current_user.organization_id}"
        )
        return error_response(
            "Trigger form not found or access denied", status_code=404
        )

    steps = [_frontend_step_to_backend(s) for s in data["steps"]]
    workflow = ApprovalWorkflow(
        name=data["name"],
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
        f"Workflow created. ID: {workflow.id}, Org: {current_user.organization_id}, User: {current_user.id}"
    )
    return success_response(
        data=_serialize_workflow(workflow),
        message="Approval workflow created successfully",
        status_code=201,
    )


@workflow_bp.route("/", methods=["GET"])
@swag_from(
    {
        "tags": ["Workflow"],
        "responses": {
            "200": {"description": "List all workflows for the current organization."}
        },
    }
)
@jwt_required()
def list_workflows():
    """List all workflows for the current organization."""
    current_user = get_current_user()
    trigger_form_id = request.args.get("trigger_form_id")
    filters = {"organization_id": current_user.organization_id, "is_deleted": False}

    if trigger_form_id:
        filters["trigger_form_id"] = trigger_form_id

    workflows = ApprovalWorkflow.objects(**filters)
    result = [_serialize_workflow(w) for w in workflows]

    app_logger.info(
        f"list_workflows: found {len(result)} workflows for org {current_user.organization_id}"
    )
    return success_response(data={"items": result, "total": len(result)})


@workflow_bp.route("/<workflow_id>", methods=["GET"])
@swag_from(
    {
        "tags": ["Workflow"],
        "responses": {"200": {"description": "Get detailed workflow definition."}},
        "parameters": [
            {"name": "workflow_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
def get_workflow(workflow_id):
    """Get detailed workflow definition."""
    current_user = get_current_user()
    workflow_uuid, err = _parse_uuid(workflow_id, "workflow_id")
    if err:
        return err

    workflow = ApprovalWorkflow.objects(
        id=workflow_uuid,
        organization_id=current_user.organization_id,
        is_deleted=False,
    ).first()

    if not workflow:
        app_logger.warning(
            f"get_workflow: {workflow_uuid} not found for org {current_user.organization_id}"
        )
        return error_response("Workflow not found", status_code=404)

    return success_response(data=_serialize_workflow(workflow))


@workflow_bp.route("/pending", methods=["GET"])
@jwt_required()
def list_pending_approvals():
    """List workflows with pending approvals for current user."""
    current_user = get_current_user()
    from services.workflow_service import WorkflowInstanceService

    service = WorkflowInstanceService()
    pending = service.list_pending_approvals(
        user_id=str(current_user.id), organization_id=current_user.organization_id
    )
    pending_dicts = [p.model_dump() for p in pending]
    app_logger.info(
        f"list_pending_approvals: found {len(pending_dicts)} pending for user {current_user.id}"
    )
    return success_response(data={"items": pending_dicts, "total": len(pending_dicts)})


@workflow_bp.route("/<workflow_id>", methods=["PUT"])
@swag_from(
    {
        "tags": ["Workflow"],
        "responses": {"200": {"description": "Update an existing workflow."}},
        "parameters": [
            {"name": "workflow_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
def update_workflow(workflow_id):
    """Update an existing workflow."""
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}

    workflow_uuid, err = _parse_uuid(workflow_id, "workflow_id")
    if err:
        return err

    workflow = ApprovalWorkflow.objects(
        id=workflow_uuid,
        organization_id=current_user.organization_id,
        is_deleted=False,
    ).first()

    if not workflow:
        app_logger.warning(
            f"update_workflow: {workflow_uuid} not found for org {current_user.organization_id}"
        )
        return error_response("Workflow not found", status_code=404)

    if "name" in data:
        workflow.name = data["name"]
    if "description" in data:
        workflow.description = data["description"]
    if "status" in data:
        workflow.status = data["status"]
    if "steps" in data:
        workflow.steps = [_frontend_step_to_backend(s) for s in data["steps"]]

    workflow.save()
    audit_logger.info(
        f"Workflow updated. ID: {workflow.id}, Org: {current_user.organization_id}, User: {current_user.id}"
    )
    return success_response(
        data=_serialize_workflow(workflow), message="Workflow updated successfully"
    )


@workflow_bp.route("/<workflow_id>", methods=["DELETE"])
@swag_from(
    {
        "tags": ["Workflow"],
        "responses": {"200": {"description": "Soft-delete a workflow."}},
        "parameters": [
            {"name": "workflow_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
def delete_workflow(workflow_id):
    """Soft-delete a workflow."""
    current_user = get_current_user()
    workflow_uuid, err = _parse_uuid(workflow_id, "workflow_id")
    if err:
        return err

    workflow = ApprovalWorkflow.objects(
        id=workflow_uuid,
        organization_id=current_user.organization_id,
        is_deleted=False,
    ).first()

    if not workflow:
        app_logger.warning(
            f"delete_workflow: {workflow_uuid} not found for org {current_user.organization_id}"
        )
        return error_response("Workflow not found", status_code=404)

    workflow.soft_delete()
    audit_logger.info(
        f"Workflow soft-deleted. ID: {workflow_uuid}, Org: {current_user.organization_id}, User: {current_user.id}"
    )
    return success_response(message="Workflow deleted successfully")


@workflow_bp.route("/forms/<form_id>/workflows", methods=["GET"])
@jwt_required()
def list_form_workflows(form_id):
    """List all workflows associated with a specific form."""
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
    """Create a workflow scoped to a specific form."""
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    data["trigger_form_id"] = form_id

    if "steps" not in data:
        return error_response("Missing required field: steps", status_code=400)

    trigger_form_uuid, err = _parse_uuid(form_id, "trigger_form_id")
    if err:
        return err

    trigger_form = Form.objects(
        id=trigger_form_uuid, organization_id=current_user.organization_id
    ).first()
    if not trigger_form:
        return error_response(
            "Trigger form not found or access denied", status_code=404
        )

    steps = [_frontend_step_to_backend(s) for s in data["steps"]]
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
        f"Form workflow created. ID: {workflow.id}, FormID: {form_id}, Org: {current_user.organization_id}, User: {current_user.id}"
    )
    return success_response(
        data=_serialize_workflow(workflow),
        message="Approval workflow created successfully",
        status_code=201,
    )
