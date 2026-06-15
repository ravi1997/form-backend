from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask_jwt_extended import create_access_token

from models.User import User
from services.api_key_service import ApiKeyService
from routes.v1.external_api_route import external_api_bp


def _register_external_api(app):
    try:
        app.register_blueprint(external_api_bp, url_prefix="/api/v1/external")
    except AssertionError:
        pass


def _auth_headers(app):
    token = create_access_token(identity="user-1")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _make_user():
    user = User(
        username="external-api-user",
        email="external-api-user@example.com",
        user_type="employee",
        organization_id="org-ext",
        roles=["admin"],
        is_admin=True,
        is_active=True,
        is_deleted=False,
    )
    user.set_password("password123")
    user.save()
    return user


def test_get_uhid_details_returns_503_when_unconfigured(app, monkeypatch):
    _register_external_api(app)
    monkeypatch.delenv("AIIMS_UHID_API_URL", raising=False)
    monkeypatch.delenv("UHID_API_URL", raising=False)
    monkeypatch.delenv("EXTERNAL_UHID_API_URL", raising=False)

    client = app.test_client()
    response = client.get(
        "/api/v1/external/uhid/1234",
        headers=_auth_headers(app),
    )

    assert response.status_code == 503
    assert "not configured" in response.get_json()["error"]["message"].lower()


@patch("routes.v1.external_api_route.NotificationService._call_external_api")
def test_send_mail_uses_notification_service(mock_call_external_api, app):
    _register_external_api(app)
    mock_call_external_api.return_value = {"message_id": "mail-1"}
    client = app.test_client()

    response = client.post(
        "/api/v1/external/mail",
        headers=_auth_headers(app),
        json={
            "config": {"url": "https://mail.example.com/send"},
            "data": {"subject": "Hello"},
        },
    )

    assert response.status_code == 200
    mock_call_external_api.assert_called_once_with(
        {"url": "https://mail.example.com/send"},
        {"subject": "Hello"},
    )


@patch("routes.v1.external_api_route.get_sms_service")
def test_send_sms_uses_sms_service(mock_get_sms_service, app):
    _register_external_api(app)
    sms_result = SimpleNamespace(
        success=True,
        message_id="sms-1",
        status_code=200,
        error_message=None,
    )
    sms_service = MagicMock()
    sms_service.send_sms.return_value = sms_result
    mock_get_sms_service.return_value = sms_service
    client = app.test_client()

    response = client.post(
        "/api/v1/external/sms",
        headers=_auth_headers(app),
        json={"mobile": "9999999999", "message": "Hello"},
    )

    assert response.status_code == 200
    sms_service.send_sms.assert_called_once_with("9999999999", "Hello")


@patch("routes.v1.external_api_route.NotificationService._call_external_api")
def test_send_mail_accepts_api_key_auth(mock_call_external_api, app, db_connection):
    _register_external_api(app)
    user = _make_user()
    api_key = ApiKeyService.create_api_key(
        organization_id="org-ext",
        name="External Mail",
        created_by=user,
    )
    mock_call_external_api.return_value = {"message_id": "mail-2"}
    client = app.test_client()

    response = client.post(
        "/api/v1/external/mail",
        headers={"X-API-Key": api_key.raw_key, "Content-Type": "application/json"},
        json={
            "config": {"url": "https://mail.example.com/send"},
            "data": {"subject": "Hello"},
        },
    )

    assert response.status_code == 200
    mock_call_external_api.assert_called_once_with(
        {"url": "https://mail.example.com/send"},
        {"subject": "Hello"},
    )
