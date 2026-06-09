import hashlib
import hmac

from unittest.mock import Mock, patch

from config.settings import settings
from services.webhook_service import WebhookService


@patch("services.webhook_service.redis_service")
@patch("services.webhook_service.requests.post")
@patch("services.webhook_service.WebhookDeliveryLog")
def test_send_webhook_adds_ridp_signature(mock_log_model, mock_post, mock_redis):
    payload = {
        "organization_id": "org-1",
        "event": "submission.created",
        "data": {"id": "sub-1", "score": 9},
    }
    response = Mock(status_code=200)
    response.raise_for_status.return_value = None
    mock_post.return_value = response
    mock_log_model.objects.return_value.first.return_value = None

    result = WebhookService.send_webhook(
        url="https://example.com/webhook",
        payload=payload,
        webhook_id="webhook-1",
        form_id="form-1",
        headers={"X-Webhook-Source": "ridp"},
        timeout=5,
    )

    sent_headers = mock_post.call_args.kwargs["headers"]
    expected_digest = hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"),
        WebhookService._canonical_payload(payload),
        hashlib.sha256,
    ).hexdigest()

    assert sent_headers["X-Webhook-Source"] == "ridp"
    assert sent_headers["X-RIDP-Signature"] == f"sha256={expected_digest}"
    assert result["headers"]["X-RIDP-Signature"] == f"sha256={expected_digest}"
    assert mock_log_model.from_record.called
