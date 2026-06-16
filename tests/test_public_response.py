from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4
from models.User import User
from models.Form import Form
from models.Response import FormResponse
from services.api_key_service import ApiKeyService
from routes.v1.forms_misc_route import forms_misc_bp

def _register_forms_misc(app):
    try:
        app.register_blueprint(forms_misc_bp, url_prefix="/api/v1/forms")
    except AssertionError:
        pass

def _make_user():
    user = User(
        username="form-submitter",
        email="submitter@example.com",
        user_type="employee",
        organization_id="org-submit",
        roles=["admin"],
        is_admin=True,
        is_active=True,
        is_deleted=False,
    )
    user.set_password("password123")
    user.save()
    return user

def _make_form(org_id, creator_id, expires_at=None, publish_at=None):
    slug_val = f"public-form-{uuid4().hex[:8]}"
    form = Form(
        id=uuid4(),
        title="Public Form",
        slug=slug_val,
        organization_id=org_id,
        created_by=str(creator_id),
        is_deleted=False,
        expires_at=expires_at,
        publish_at=publish_at,
    )
    form.save()
    return form

def test_submit_public_response_requires_api_key(app, db_connection):
    _register_forms_misc(app)
    client = app.test_client()
    form_id = str(uuid4())
    
    response = client.post(
        f"/api/v1/forms/{form_id}/responses",
        json={"data": {"q1": "test"}}
    )
    assert response.status_code == 401
    assert "header is required" in response.get_json()["error"]["message"].lower()

def test_submit_public_response_invalid_api_key(app, db_connection):
    _register_forms_misc(app)
    client = app.test_client()
    form_id = str(uuid4())
    
    response = client.post(
        f"/api/v1/forms/{form_id}/responses",
        headers={"X-API-Key": "invalid_key"},
        json={"data": {"q1": "test"}}
    )
    assert response.status_code == 403
    assert "invalid" in response.get_json()["error"]["message"].lower()

@patch("services.response_service.FormResponseService.validate_payload", return_value=(True, {}, {}, {}))
def test_submit_public_response_success(mock_validate, app, db_connection):
    _register_forms_misc(app)
    user = _make_user()
    api_key = ApiKeyService.create_api_key(
        organization_id="org-submit",
        name="Submit Key",
        created_by=user
    )
    form = _make_form("org-submit", user.id)
    client = app.test_client()
    
    response = client.post(
        f"/api/v1/forms/{form.id}/responses",
        headers={"X-API-Key": api_key.raw_key},
        json={
            "data": {"q1": "hello"},
            "answers": {"q1": {"value": "hello", "display_value": "hello"}},
            "repeat_groups": {}
        }
    )
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert "response_id" in data
    
    # Check it actually saved in the DB
    resp_obj = FormResponse.objects.get(id=data["response_id"])
    assert resp_obj.organization_id == "org-submit"
    assert resp_obj.data == {"q1": "hello"}
    assert resp_obj.answers == {"q1": {"value": "hello", "display_value": "hello"}}

def test_submit_public_response_expired_form(app, db_connection):
    _register_forms_misc(app)
    user = _make_user()
    api_key = ApiKeyService.create_api_key(
        organization_id="org-submit",
        name="Submit Key",
        created_by=user
    )
    expired_time = datetime.now(timezone.utc) - timedelta(days=1)
    form = _make_form("org-submit", user.id, expires_at=expired_time)
    client = app.test_client()
    
    response = client.post(
        f"/api/v1/forms/{form.id}/responses",
        headers={"X-API-Key": api_key.raw_key},
        json={"data": {"q1": "hello"}}
    )
    assert response.status_code == 400
    assert "expired" in response.get_json()["error"]["message"].lower()
