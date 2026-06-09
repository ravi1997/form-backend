from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

import pytest

from routes.v1.form.responses import sync_responses
from services.tombstone_service import TombstoneService
from tasks.form_tasks import cleanup_deleted_records


pytestmark = pytest.mark.usefixtures("db_connection")


def test_tombstone_service_records_and_lists_since():
    service = TombstoneService()
    tombstone = SimpleNamespace(
        organization_id="org-1",
        entity_type="forms",
        entity_id="form-1",
        deleted_at=SimpleNamespace(isoformat=lambda: "2026-06-01T00:00:00+00:00"),
        save=MagicMock(),
    )

    with patch("services.tombstone_service.Tombstone", return_value=tombstone), patch(
        "services.tombstone_service.audit_logger"
    ):
        recorded = service.record_delete("org-1", "forms", "form-1")

    assert recorded.entity_type == "forms"
    assert recorded.entity_id == "form-1"


def test_tombstone_service_prunes_old_records():
    service = TombstoneService()
    mock_objects = MagicMock()
    mock_objects.return_value.delete.return_value = 3

    with patch("services.tombstone_service.Tombstone.objects", mock_objects):
        deleted_count = service.prune_old_tombstones(retention_days=7)

    assert deleted_count == 3


def test_sync_responses_includes_tombstones(app):
    current_user = SimpleNamespace(id="user-1", organization_id="org-1")
    form = SimpleNamespace(id="11111111-1111-1111-1111-111111111111")
    tombstones = [
        {
            "entity_type": "forms",
            "entity_id": "form-deleted-1",
            "deleted_at": "2026-06-01T00:00:00+00:00",
        }
    ]

    with app.test_request_context(
        "/mahasangraha/api/v1/forms/11111111-1111-1111-1111-111111111111/responses/sync?last_synced_at=2026-06-01T00:00:00Z",
        method="POST",
        json={"submissions": []},
    ):
        with patch("routes.v1.form.responses.get_current_user", return_value=current_user), patch(
            "routes.v1.form.responses.Form.objects"
        ) as mock_form_objects, patch(
            "routes.v1.form.responses.has_form_permission", return_value=True
        ), patch(
            "services.tombstone_service.TombstoneService"
        ) as mock_tombstone_service:
            mock_form_objects.get.return_value = form
            mock_tombstone_service.return_value.list_since.return_value = tombstones

            response, status = sync_responses.__wrapped__(
                "11111111-1111-1111-1111-111111111111"
            )

    assert status == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["tombstones"] == tombstones


def test_cleanup_deleted_records_routes_hard_deletes_through_services():
    form = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        deleted_at=datetime.now(timezone.utc) - timedelta(days=60),
        organization_id="org-1",
    )
    response = SimpleNamespace(
        id="22222222-2222-2222-2222-222222222222",
        deleted_at=datetime.now(timezone.utc) - timedelta(days=60),
        organization_id="org-1",
    )

    form_service_mock = MagicMock()
    response_service_mock = MagicMock()
    form_query = [form]
    response_query = [response]

    with patch("models.Form.Form.objects", return_value=form_query), patch(
        "models.Response.FormResponse.objects", return_value=response_query
    ), patch("services.form_service.FormService", return_value=form_service_mock), patch(
        "services.response_service.FormResponseService", return_value=response_service_mock
    ), patch("tasks.form_tasks.audit_logger"), patch(
        "tasks.form_tasks.app_logger"
    ):
        result = cleanup_deleted_records.run(retention_days=30, dry_run=False)

    assert result["status"] == "success"
    form_service_mock.delete.assert_called_once_with(
        "11111111-1111-1111-1111-111111111111",
        organization_id="org-1",
        hard_delete=True,
    )
    response_service_mock.delete.assert_called_once_with(
        "22222222-2222-2222-2222-222222222222",
        organization_id="org-1",
        hard_delete=True,
    )
