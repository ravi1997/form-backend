import pytest
import uuid
from models.Form import Project
from models.FormResponseWorkflow import FormResponseWorkflow, WorkflowApprovalStep

def test_workflow_sequential_transitions(app, db_connection):
    # 1. Create a Workflow instance
    workflow_id = uuid.uuid4()
    workflow = FormResponseWorkflow(
        id=workflow_id,
        response_id="response-abc-123",
        project_id="project-xyz-456",
        status="pending",
        steps=[
            WorkflowApprovalStep(
                step_name="Department Review",
                assigned_roles=["manager"],
                status="pending"
            ),
            WorkflowApprovalStep(
                step_name="Admin Sanction",
                assigned_roles=["admin"],
                status="pending"
            )
        ]
    ).save()

    # Validate initialization
    assert FormResponseWorkflow.objects(id=workflow_id).count() == 1
    wf = FormResponseWorkflow.objects(id=workflow_id).first()
    assert wf.status == "pending"
    assert len(wf.steps) == 2
    assert wf.steps[0].step_name == "Department Review"

    # 2. Action Step 1 (Approve)
    wf.steps[0].status = "approved"
    wf.steps[0].actioned_by = "user-manager-88"
    wf.status = "in_progress"
    wf.save()

    # Verify transition state
    wf.reload()
    assert wf.status == "in_progress"
    assert wf.steps[0].status == "approved"
    assert wf.steps[0].actioned_by == "user-manager-88"
    assert wf.steps[1].status == "pending"
