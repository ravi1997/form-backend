import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from mongoengine.errors import DoesNotExist
from routes.v1.form import form_bp

pytestmark = pytest.mark.usefixtures("db_connection")

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture(autouse=True)
def register_form_blueprint(app):
    try:
        app.register_blueprint(form_bp, url_prefix="/form/api/v1/forms")
    except AssertionError:
        pass
    yield

def test_public_submit_success(client):
    """Verify that a public, published, active form accepts submissions anonymously."""
    mock_form = MagicMock()
    mock_form.id = "public-form-123"
    mock_form.status = "published"
    mock_form.is_public = True
    mock_form.expires_at = None
    mock_form.publish_at = None
    mock_form.organization_id = "org-test-123"

    mock_response = MagicMock()
    mock_response.id = "response-999"

    mock_objects = MagicMock()
    mock_objects.get.return_value = mock_form

    with patch("routes.v1.form.misc.Form.objects", mock_objects), \
         patch("services.response_service.FormResponseService.create_submission", return_value=mock_response):
        
        response = client.post(
            "/form/api/v1/forms/public-form-123/public-submit",
            json={"data": {"q-1": "answer"}}
        )
        
        assert response.status_code == 201
        json_data = response.get_json()
        assert json_data["success"] is True
        assert json_data["data"]["response_id"] == "response-999"

def test_public_submit_not_public(client):
    """Verify that a private (is_public=False) form rejects submissions."""
    mock_form = MagicMock()
    mock_form.id = "private-form-123"
    mock_form.status = "published"
    mock_form.is_public = False
    mock_form.expires_at = None
    mock_form.publish_at = None

    mock_objects = MagicMock()
    mock_objects.get.return_value = mock_form

    with patch("routes.v1.form.misc.Form.objects", mock_objects):
        response = client.post(
            "/form/api/v1/forms/private-form-123/public-submit",
            json={"data": {}}
        )
        assert response.status_code == 403
        json_data = response.get_json()
        assert json_data["success"] is False
        assert "not public" in json_data["error"]["message"].lower()

def test_public_submit_not_published(client):
    """Verify that a draft form rejects submissions."""
    mock_form = MagicMock()
    mock_form.id = "draft-form-123"
    mock_form.status = "draft"
    mock_form.is_public = True
    mock_form.expires_at = None
    mock_form.publish_at = None

    mock_objects = MagicMock()
    mock_objects.get.return_value = mock_form

    with patch("routes.v1.form.misc.Form.objects", mock_objects):
        response = client.post(
            "/form/api/v1/forms/draft-form-123/public-submit",
            json={"data": {}}
        )
        assert response.status_code == 403
        json_data = response.get_json()
        assert json_data["success"] is False
        assert "not accepting submissions" in json_data["error"]["message"].lower()

def test_public_submit_expired(client):
    """Verify that an expired form rejects submissions."""
    mock_form = MagicMock()
    mock_form.id = "expired-form-123"
    mock_form.status = "published"
    mock_form.is_public = True
    mock_form.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    mock_form.publish_at = None

    mock_objects = MagicMock()
    mock_objects.get.return_value = mock_form

    with patch("routes.v1.form.misc.Form.objects", mock_objects):
        response = client.post(
            "/form/api/v1/forms/expired-form-123/public-submit",
            json={"data": {}}
        )
        assert response.status_code == 403
        json_data = response.get_json()
        assert json_data["success"] is False
        assert "expired" in json_data["error"]["message"].lower()

def test_public_submit_scheduled_future(client):
    """Verify that a future-scheduled form rejects submissions."""
    mock_form = MagicMock()
    mock_form.id = "future-form-123"
    mock_form.status = "published"
    mock_form.is_public = True
    mock_form.expires_at = None
    mock_form.publish_at = datetime.now(timezone.utc) + timedelta(days=1)

    mock_objects = MagicMock()
    mock_objects.get.return_value = mock_form

    with patch("routes.v1.form.misc.Form.objects", mock_objects):
        response = client.post(
            "/form/api/v1/forms/future-form-123/public-submit",
            json={"data": {}}
        )
        assert response.status_code == 403
        json_data = response.get_json()
        assert json_data["success"] is False
        assert "not yet available" in json_data["error"]["message"].lower()

def test_public_submit_form_not_found(client):
    """Verify that looking up a non-existent form returns 404."""
    mock_objects = MagicMock()
    mock_objects.get.side_effect = DoesNotExist

    with patch("routes.v1.form.misc.Form.objects", mock_objects):
        response = client.post(
            "/form/api/v1/forms/missing-form-123/public-submit",
            json={"data": {}}
        )
        assert response.status_code == 404
        json_data = response.get_json()
        assert json_data["success"] is False
        assert "not found" in json_data["error"]["message"].lower()
