import pytest
from unittest.mock import patch
from tasks.notification_tasks import (
    process_notification_triggers,
    long_running_computation,
)


def test_long_running_computation():
    """Test the example computation task directly."""
    # Using .run() or calling directly bypasses Celery's async delivery
    # which is preferred for unit testing task logic.
    result = long_running_computation("test_input")
    assert result["status"] == "completed"
    assert "result" in result


@patch("services.notification_service.NotificationService.execute_triggers")
def test_process_notification_triggers_task(mock_execute):
    """Test the trigger processing task calls NotificationService."""
    triggers_data = [
        {"name": "test_webhook", "action_type": "webhook", "is_active": True}
    ]
    context_data = {"event": "submission", "form_id": "123"}

    process_notification_triggers(triggers_data, context_data)

    mock_execute.assert_called_once_with(triggers_data, context_data)


@patch("tasks.notification_tasks.process_notification_triggers.retry")
@patch("services.notification_service.NotificationService.execute_triggers")
def test_process_notification_triggers_retry(mock_execute, mock_retry):
    """Test task retry logic on service failure."""
    # Mocking a retry exception which is what Celery expects
    from celery.exceptions import Retry

    mock_retry.side_effect = Retry("Retrying...")

    mock_execute.side_effect = Exception("Temporary failure")

    triggers_data = [{"name": "test"}]
    context_data = {}

    with pytest.raises(Retry):
        # Celery injects 'self' automatically when called, and we've mocked the task's .retry method
        process_notification_triggers(triggers_data, context_data)

    assert mock_retry.called
