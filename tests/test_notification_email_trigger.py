from unittest.mock import patch

from tasks.notification_tasks import process_single_trigger


@patch("services.notification_service.NotificationService._call_external_api")
@patch("services.notification_service.NotificationObservability.increment_attempt")
@patch("services.notification_service.NotificationObservability.increment_success")
def test_email_notification_trigger_uses_external_api(
    mock_success, mock_attempt, mock_call_api
):
    mock_call_api.return_value = {"ok": True}

    result = process_single_trigger.run(
        {
            "name": "email alert",
            "action_type": "email_notification",
            "action_config": {"url": "https://example.com/email"},
        },
        {"form_id": "form-1"},
    )

    mock_call_api.assert_called_once()
    mock_success.assert_called_once_with("email_notification")
    mock_attempt.assert_called_once_with("email_notification")
    assert result is None
