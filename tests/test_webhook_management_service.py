from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from models.components import Trigger
from services.webhook_service import WebhookService


def _make_form():
    trigger = Trigger(
        name="Patient lookup webhook",
        event_type="on_submit",
        action_type="webhook",
        action_config={
            "url": "https://example.com/webhook",
            "headers": {"X-Test": "1"},
        },
        is_active=True,
        order="2",
    )
    trigger.meta_data = {"webhook_id": "hook-1", "created_at": "2026-06-12T00:00:00Z"}

    other_trigger = Trigger(
        name="Email alert",
        event_type="on_submit",
        action_type="email",
        action_config={"recipient": "ops@example.com"},
        is_active=True,
        order="1",
    )

    form = SimpleNamespace(
        id="form-1",
        created_by="user-1",
        editors=["user-2"],
        triggers=[other_trigger, trigger],
        save=MagicMock(),
    )
    return form


def _objects_factory(form):
    def _query(*args, **kwargs):
        if kwargs.get("id") == "form-1":
            return SimpleNamespace(first=lambda: form)
        if kwargs.get("is_deleted") is False:
            return [form]
        if kwargs.get("triggers__action_type") == "webhook":
            return [form]
        return SimpleNamespace(first=lambda: None)

    return _query


@patch("services.webhook_service.Form.objects")
def test_list_webhooks_returns_persisted_triggers(mock_objects):
    form = _make_form()
    mock_objects.side_effect = _objects_factory(form)

    items = WebhookService.list_webhooks("form-1", "user-1")

    assert len(items) == 1
    assert items[0]["id"] == "hook-1"
    assert items[0]["form_id"] == "form-1"


@patch("services.webhook_service.Form.objects")
def test_create_webhook_persists_new_trigger(mock_objects):
    form = _make_form()
    form.triggers = []
    mock_objects.side_effect = _objects_factory(form)

    created = WebhookService.create_webhook(
        form_id="form-1",
        user_id="user-1",
        name="New webhook",
        action_config={"url": "https://example.com/new"},
    )

    assert created["name"] == "New webhook"
    assert created["action_config"]["url"] == "https://example.com/new"
    assert created["id"]
    assert form.save.called
    assert len(form.triggers) == 1
    assert form.triggers[0].meta_data["webhook_id"] == created["id"]


@patch("services.webhook_service.Form.objects")
def test_delete_webhook_removes_trigger(mock_objects):
    form = _make_form()
    mock_objects.side_effect = _objects_factory(form)

    result = WebhookService.delete_webhook("hook-1", "user-1")

    assert result is True
    assert form.save.called
    assert all(
        getattr(trigger, "action_type", None) != "webhook"
        for trigger in form.triggers
    )


@patch("services.webhook_service.Form.objects")
@patch("services.webhook_service.WebhookService.send_webhook")
def test_trigger_test_uses_persisted_webhook(mock_send_webhook, mock_objects):
    form = _make_form()
    mock_objects.side_effect = _objects_factory(form)
    mock_send_webhook.return_value = {"delivery_id": "delivery-1"}

    result = WebhookService.trigger_test("hook-1", "user-1")

    mock_send_webhook.assert_called_once()
    assert result["delivery_id"] == "delivery-1"
