from routes.v1.form.ai import get_field_suggestions


def _unwrap(route):
    while hasattr(route, "__wrapped__"):
        route = route.__wrapped__
    return route


def test_ai_field_suggestions_require_current_form(app):
    with app.test_request_context("/ai/suggestions", json={}):
        response, status_code = _unwrap(get_field_suggestions)()

    assert status_code == 400
    assert response.get_json()["error"] == "current_form is required"


def test_ai_field_suggestions_delegate_to_service(app, monkeypatch):
    monkeypatch.setattr(
        "routes.v1.form.ai.AIService.get_suggestions",
        classmethod(lambda cls, current_form: [{"label": "Demo", "field_type": "input"}]),
    )

    with app.test_request_context(
        "/ai/suggestions",
        json={"current_form": {"sections": [{"questions": []}]}},
    ):
        response, status_code = _unwrap(get_field_suggestions)()

    assert status_code == 200
    assert response.get_json()[0]["label"] == "Demo"
