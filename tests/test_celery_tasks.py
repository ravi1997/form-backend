import pytest
from unittest.mock import patch
from config.celery import celery_app
from tasks.notification_tasks import (
    process_notification_triggers,
    process_single_trigger,
    long_running_computation,
    process_notification_retry_queue_task,
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


class _FakeRetryQuerySet:
    def __init__(self, logs):
        self._logs = logs

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, batch_size):
        return self._logs[:batch_size]


def _make_notification_log(channel="webhook", payload=None, attempt_count=0):
    log = type("NotificationLogStub", (), {})()
    log.id = "log-1"
    log.channel = channel
    log.payload = payload or {"action_config": {"url": "http://example.com"}}
    log.attempt_count = attempt_count
    log.status = "failed"
    log.response = {}
    log.error_message = None
    log.sent_at = None
    log.updated_at = None
    log.save = lambda: None
    return log


@patch("tasks.notification_tasks.NotificationLog.objects")
@patch("tasks.notification_tasks.NotificationService._call_webhook")
def test_process_notification_retry_queue_task_delivers_failed_log(
    mock_call_webhook, mock_objects
):
    log = _make_notification_log()
    mock_call_webhook.return_value = {"ok": True}
    mock_objects.return_value = _FakeRetryQuerySet([log])

    result = process_notification_retry_queue_task()

    assert result == {
        "status": "completed",
        "processed": 1,
        "succeeded": 1,
        "failed": 0,
        "skipped": 0,
    }
    assert log.status == "sent"
    assert log.attempt_count == 1
    assert log.response == {"ok": True}
    assert log.error_message == ""


@patch("tasks.notification_tasks.NotificationLog.objects")
@patch("tasks.notification_tasks.NotificationService._call_webhook", side_effect=Exception("boom"))
def test_process_notification_retry_queue_task_marks_failure(
    mock_call_webhook, mock_objects
):
    log = _make_notification_log()
    mock_objects.return_value = _FakeRetryQuerySet([log])

    result = process_notification_retry_queue_task()

    assert result["failed"] == 1
    assert log.status == "failed"
    assert log.attempt_count == 1
    assert log.error_message == "boom"


@patch("tasks.notification_tasks.NotificationLog.objects")
def test_process_notification_retry_queue_task_skips_unsupported_channel(
    mock_objects,
):
    log = _make_notification_log(channel="sms")
    mock_objects.return_value = _FakeRetryQuerySet([log])

    result = process_notification_retry_queue_task()

    assert result["skipped"] == 1
    assert log.status == "skipped"
    assert log.attempt_count == 1
    assert "Unsupported notification channel" in log.error_message
