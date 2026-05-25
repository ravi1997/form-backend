import pytest
from unittest.mock import MagicMock, patch
from services.task_service import TaskService


def test_task_service_get_status_from_redis():
    """Verify that get_status returns the correct dictionary if the task is tracked in Redis."""
    mock_redis_status = {
        "state": "PROCESSING",
        "result": {"form_id": "test_form"},
        "error": None,
        "traceback": None,
        "current": 5,
        "total": 10,
    }

    with patch("services.task_observability_service.task_observability_service.get_task_status", return_value=mock_redis_status):
        service = TaskService()
        status = service.get_status("test-task-123")

        assert status["task_id"] == "test-task-123"
        assert status["state"] == "PROCESSING"
        assert status["result"] == {"form_id": "test_form"}
        assert status["error"] is None
        assert status["current_progress"] == 5
        assert status["total_progress"] == 10


def test_task_service_get_status_fallback_to_celery():
    """Verify that get_status falls back to Celery AsyncResult if not found in Redis."""
    # Mock Redis returning None
    mock_celery_task = MagicMock()
    mock_celery_task.ready.return_value = True
    mock_celery_task.successful.return_value = True
    mock_celery_task.result = {"data": "done"}
    mock_celery_task.state = "SUCCESS"

    with patch("services.task_observability_service.task_observability_service.get_task_status", return_value=None), \
         patch("config.celery.celery_app.AsyncResult", return_value=mock_celery_task):
        
        service = TaskService()
        status = service.get_status("test-task-456")

        assert status["task_id"] == "test-task-456"
        assert status["state"] == "SUCCESS"
        assert status["result"] == {"data": "done"}
        assert status["error"] is None


def test_get_task_status_endpoint(app):
    """Test that the public GET /api/v1/tasks/<task_id> endpoint works and returns success."""
    from routes.v1.task_route import task_bp
    
    # Register blueprint if not already registered on custom app
    try:
        app.register_blueprint(task_bp, url_prefix="/api/v1/tasks")
    except AssertionError:
        # already registered
        pass

    mock_status = {
        "task_id": "test-123",
        "state": "SUCCESS",
        "result": {"status": "cloned"},
        "error": None,
        "traceback": None,
        "current_progress": None,
        "total_progress": None,
    }

    # Use test client
    with app.test_client() as client, \
         patch("routes.v1.task_route.jwt_required", lambda x=None: lambda f: f), \
         patch("flask_jwt_extended.view_decorators.verify_jwt_in_request") as mock_verify, \
         patch("services.task_service.task_service.get_status", return_value=mock_status):

        response = client.get("/api/v1/tasks/test-123")
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data["success"] is True
        assert json_data["data"]["task_id"] == "test-123"
        assert json_data["data"]["state"] == "SUCCESS"


def test_get_admin_task_status_endpoint(app):
    """Test that the admin GET /api/v1/admin/tasks/<task_id> endpoint works for admins."""
    from routes.v1.admin.task_route import admin_task_bp
    
    try:
        app.register_blueprint(admin_task_bp, url_prefix="/api/v1/admin/tasks")
    except AssertionError:
        # already registered
        pass

    mock_status = {
        "task_id": "test-admin-123",
        "state": "PROCESSING",
        "result": None,
        "error": None,
        "traceback": None,
        "current_progress": 2,
        "total_progress": 5,
    }

    # We mock require_roles to allow access, bypass JWT check
    with app.test_client() as client, \
         patch("utils.security.verify_jwt_in_request") as mock_verify_jwt, \
         patch("utils.security.get_jwt", return_value={"roles": ["admin"]}), \
         patch("services.task_service.task_service.get_status", return_value=mock_status):

        response = client.get("/api/v1/admin/tasks/test-admin-123")
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data["success"] is True
        assert json_data["data"]["task_id"] == "test-admin-123"
        assert json_data["data"]["state"] == "PROCESSING"
        assert json_data["data"]["current_progress"] == 2
