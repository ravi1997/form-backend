import pytest
from unittest.mock import patch
from config.celery import celery_app
from tasks.notification_tasks import (
    process_notification_triggers,
    process_single_trigger,
    long_running_computation,
)
from tasks.ai_tasks import async_export_to_olap


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


def test_async_export_to_olap_routes_to_single_writer_queue():
    route = celery_app.conf.task_routes["tasks.ai_tasks.async_export_to_olap"]
    assert route["queue"] == "analytics_write"


@patch("services.analytics_stream_service.analytics_stream_service.process_submission_event")
def test_async_export_to_olap_invokes_analytics_stream(mock_process):
    payload = {
        "response_id": "resp-1",
        "form_id": "form-1",
        "organization_id": "org-1",
        "timestamp": "2026-06-06T00:00:00Z",
        "data": {"field": "value"},
    }

    async_export_to_olap.run(payload)

    mock_process.assert_called_once_with(payload)
