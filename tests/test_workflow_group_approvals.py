from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.workflow_service import WorkflowInstanceService


def _make_workflow_instance():
    step = SimpleNamespace(
        order=1,
        approvers=[],
        approver_groups=["group-1"],
        required_approvals=1,
        step_name="Review",
    )
    workflow_definition = SimpleNamespace(steps=[step], is_deleted=False)
    return SimpleNamespace(
        id="instance-1",
        status="pending",
        workflow_definition=workflow_definition,
        current_step_order=1,
        step_approvals={},
        history=[],
        organization_id="org-1",
        resource_type="form_response",
        resource_id="response-1",
        save=MagicMock(),
        current_step_started_at=None,
        completed_at=None,
    )


class _Query(list):
    def first(self):
        return self[0] if self else None


def test_process_action_allows_group_members():
    instance = _make_workflow_instance()
    service = WorkflowInstanceService()
    service.model = SimpleNamespace(objects=lambda **kwargs: _Query([instance]))
    service._to_schema = lambda document: SimpleNamespace(status=document.status)

    user = SimpleNamespace(id="user-1")
    group = SimpleNamespace(
        id="group-1",
        members=[SimpleNamespace(id="user-1")],
        organization_id="org-1",
        is_deleted=False,
        is_active=True,
    )

    with patch("services.workflow_service.User", new=SimpleNamespace(objects=SimpleNamespace(get=lambda **kwargs: user))):
        with patch("services.workflow_service.UserGroup", new=SimpleNamespace(objects=lambda **kwargs: [group])):
            with patch("services.workflow_service.ApprovalLog", side_effect=lambda **kwargs: SimpleNamespace(**kwargs)):
                with patch.object(WorkflowInstanceService, "_update_resource_status") as mock_update:
                    with patch("services.workflow_service.event_bus.publish") as mock_publish:
                        result = service.process_action("instance-1", "user-1", "approve")

    assert result.status == "approved"
    assert instance.save.called
    assert mock_publish.called
    assert mock_update.called


def test_list_pending_approvals_includes_group_members():
    instance = _make_workflow_instance()
    service = WorkflowInstanceService()
    service.model = SimpleNamespace(objects=lambda **kwargs: _Query([instance]))
    service._to_schema = lambda document: document

    group = SimpleNamespace(
        id="group-1",
        members=[SimpleNamespace(id="user-1")],
        organization_id="org-1",
        is_deleted=False,
        is_active=True,
    )

    with patch("services.workflow_service.UserGroup", new=SimpleNamespace(objects=lambda **kwargs: [group])):
        pending = service.list_pending_approvals("user-1", "org-1")

    assert len(pending) == 1
