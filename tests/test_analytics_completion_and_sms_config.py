from types import SimpleNamespace

from services.ai_service import AIService
from services.ai_provider import LocalHeuristicProvider
from routes.v1.form.analytics import get_full_analytics
from services.external_sms_service import ExternalSMSService


class _FakeQueryResult(list):
    def count(self):
        return len(self)


def test_get_full_analytics_computes_completion_rate_from_real_drafts(app, monkeypatch):
    class _FakeForm:
        id = "form-1"
        versions = []

    responses = _FakeQueryResult(
        [
            SimpleNamespace(
                submitted_at=None,
                data={},
                is_draft=True,
            ),
            SimpleNamespace(
                submitted_at=None,
                data={},
                is_draft=False,
            ),
        ]
    )

    class _FakeResponseManager:
        def only(self, *args, **kwargs):
            return responses

    monkeypatch.setattr(
        "routes.v1.form.analytics.get_current_user",
        lambda: SimpleNamespace(organization_id="org-1", id="user-1"),
    )
    monkeypatch.setattr(
        "routes.v1.form.analytics.has_form_permission",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "routes.v1.form.analytics.Form",
        SimpleNamespace(objects=SimpleNamespace(get=lambda **_kwargs: _FakeForm())),
    )
    monkeypatch.setattr(
        "routes.v1.form.analytics.FormResponse",
        SimpleNamespace(objects=lambda **_kwargs: _FakeResponseManager()),
    )

    with app.test_request_context("/forms/form-1/analytics"):
        route = get_full_analytics
        while hasattr(route, "__wrapped__"):
            route = route.__wrapped__
        response, status_code = route("form-1")
        payload = response.get_json()

    assert status_code == 200
    assert payload["totalSubmissions"] == 2
    assert payload["completionRate"] == 0.5


def test_external_sms_service_requires_real_configuration(monkeypatch):
    monkeypatch.delenv("AIIMS_SMS_API_URL", raising=False)
    monkeypatch.delenv("SMS_API_URL", raising=False)

    service = ExternalSMSService()

    result = service.send_sms("9999999999", "Hello")

    assert service.api_url == ""
    assert result.success is False
    assert "not configured" in result.error_message.lower()


def test_ai_service_class_methods_are_callable(monkeypatch):
    class _FakeProvider:
        def sanitize_prompt(self, text):
            return text.strip()

        def summarize(self, text, context=None):
            return f"summary:{text}"

        def detect_anomalies(self, data):
            return [{"items": len(data)}]

        def classify_sentiment(self, text):
            return {"sentiment": "neutral", "score": 0.5}

        def classify_taxonomy(self, text, taxonomy):
            return {"tags": ["demo"], "provider": "fake"}

        def generate_embeddings(self, text):
            return [0.1, 0.2]

    monkeypatch.setattr(AIService, "provider", classmethod(lambda cls: _FakeProvider()))

    generated = AIService.generate_form("  create a demo form  ", {"name": "demo"})
    assert generated["summary"] == "summary:create a demo form"

    translated = AIService.translate_text("hello", "en", "hi")
    assert translated == "नमस्ते"

    suggestions = AIService.get_suggestions({"field": "value"})
    assert suggestions == [{"items": 1}]


def test_ai_service_local_translation_uses_heuristic_fallback(monkeypatch):
    monkeypatch.setattr(
        AIService, "provider", classmethod(lambda cls: LocalHeuristicProvider())
    )

    translated = AIService.translate_text("Hello, save the form response", "en", "hi")

    assert translated != "Hello, save the form response"
    assert "नमस्ते" in translated
    assert "फॉर्म" in translated or "उत्तर" in translated
