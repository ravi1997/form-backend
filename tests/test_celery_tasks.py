import pytest
from unittest.mock import patch
from tasks.notification_tasks import (
    process_notification_triggers,
    process_single_trigger,
    long_running_computation,
)


def test_long_running_computation():
    """Test the example computation task directly."""
    # Using .run() or calling directly bypasses Celery's async delivery
    # which is preferred for unit testing task logic.
    result = long_running_computation("test_input")
    assert result["status"] == "completed"
    assert "result" in result


@patch("tasks.notification_tasks.process_single_trigger.delay")
def test_process_notification_triggers_task(mock_delay):
    """Test the trigger processing task dispatches process_single_trigger."""
    triggers_data = [
        {"name": "test_webhook", "action_type": "webhook", "is_active": True}
    ]
    context_data = {"event": "submission", "form_id": "123"}

    process_notification_triggers(triggers_data, context_data)

    mock_delay.assert_called_once_with(triggers_data[0], context_data)


@patch("services.notification_service.NotificationService._call_webhook")
def test_process_single_trigger_webhook(mock_call_webhook):
    """Test process_single_trigger successfully processes webhook type."""
    trigger_data = {
        "name": "test_webhook",
        "action_type": "webhook",
        "action_config": {"url": "http://example.com"},
    }
    context_data = {"event": "submission"}

    process_single_trigger(trigger_data, context_data)

    mock_call_webhook.assert_called_once_with(
        trigger_data["action_config"], context_data
    )


@patch("services.notification_service.NotificationService._call_webhook")
def test_process_single_trigger_failure(mock_call_webhook):
    """Test process_single_trigger raises exception on failure to trigger Celery autoretry."""
    mock_call_webhook.side_effect = Exception("HTTP Error")
    trigger_data = {
        "name": "test_webhook",
        "action_type": "webhook",
        "action_config": {"url": "http://example.com"},
    }
    context_data = {}

    with pytest.raises(Exception) as exc:
        process_single_trigger(trigger_data, context_data)
    assert "HTTP Error" in str(exc.value)
