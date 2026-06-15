from unittest.mock import patch

from flask_jwt_extended import create_access_token


def _auth_headers(flask_app, identity="admin-1", roles=None, org_id="org-1"):
    roles = roles or ["admin"]
    with flask_app.app_context():
        token = create_access_token(
            identity=identity,
            additional_claims={"roles": roles, "organization_id": org_id},
        )
    return {"Authorization": f"Bearer {token}"}


@patch("mongoengine.connect")
def test_admin_webhook_routes(mock_connect, db_connection, redis_mock):
    from app import create_app
    from services.webhook_service import WebhookService

    flask_app = create_app()
    client = flask_app.test_client()
    headers = _auth_headers(flask_app, identity="admin-1", roles=["admin"], org_id="org-1")
    super_headers = _auth_headers(
        flask_app, identity="sa-1", roles=["superadmin"], org_id="system"
    )

    with patch.object(
        WebhookService,
        "list_webhooks",
        return_value=[{"id": "hook-1", "name": "Primary webhook"}],
    ) as mock_list, patch.object(
        WebhookService,
        "create_webhook",
        return_value={"id": "hook-2", "name": "Created webhook"},
    ) as mock_create, patch.object(
        WebhookService,
        "delete_webhook",
        return_value=True,
    ) as mock_delete, patch.object(
        WebhookService,
        "trigger_test",
        return_value={"status": "ok"},
    ) as mock_test, patch.object(
        WebhookService,
        "get_logs",
        return_value=[{"status": "delivered"}],
    ) as mock_logs:
        resp = client.get(
            "/api/internal/v1/admin/webhooks/?form_id=form-1",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"][0]["id"] == "hook-1"
        mock_list.assert_called_once_with("form-1", "admin-1")

        resp = client.post(
            "/api/internal/v1/admin/webhooks/",
            json={
                "form_id": "form-1",
                "name": "Created webhook",
                "action_config": {"url": "https://example.com/webhook"},
            },
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.get_json()["data"]["id"] == "hook-2"
        mock_create.assert_called_once()

        resp = client.post(
            "/api/internal/v1/admin/webhooks/hook-2/test",
            headers=headers,
        )
        assert resp.status_code == 200
        mock_test.assert_called_once_with("hook-2", "admin-1")

        resp = client.get(
            "/api/internal/v1/admin/webhooks/hook-2/logs?limit=25",
            headers=headers,
        )
        assert resp.status_code == 200
        mock_logs.assert_called_once_with("hook-2", "admin-1", limit=25)

        resp = client.delete(
            "/api/internal/v1/admin/webhooks/hook-2",
            headers=super_headers,
        )
        assert resp.status_code == 200
        mock_delete.assert_called_once_with("hook-2", "sa-1")


@patch("mongoengine.connect")
def test_admin_webhook_routes_require_role(mock_connect, db_connection, redis_mock):
    from app import create_app
    from flask_jwt_extended import create_access_token

    flask_app = create_app()
    client = flask_app.test_client()

    with flask_app.app_context():
        token = create_access_token(
            identity="user-1",
            additional_claims={"roles": ["user"], "organization_id": "org-1"},
        )
    resp = client.get(
        "/api/internal/v1/admin/webhooks/?form_id=form-1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
