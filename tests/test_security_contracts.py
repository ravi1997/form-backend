from utils.idempotency import require_idempotency


def test_retryable_mutation_requires_idempotency_key(app):
    @require_idempotency()
    def mutation():
        raise AssertionError("mutation must not execute without idempotency key")

    with app.test_request_context("/resource", method="POST", json={"x": 1}):
        response, status = mutation()

    assert status == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_permission_matrix_declares_critical_routes():
    import pathlib

    matrix = pathlib.Path("config/permissions.yaml").read_text()

    assert "form:publish" in matrix
    assert "response:export" in matrix
    assert "POST /form/api/v1/projects/<project_id>/forms/<form_id>/publish" in matrix
