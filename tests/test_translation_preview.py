from types import SimpleNamespace

from routes.v1.form.translation import preview_translation
from services.ai_service import AIService


def _unwrap(view):
    while hasattr(view, "__wrapped__"):
        view = view.__wrapped__
    return view


def test_preview_translation_uses_ai_service(app, monkeypatch):
    monkeypatch.setattr(AIService, "translate_text", classmethod(lambda cls, text, source_lang, target_lang: f"{text}-{target_lang}"))

    with app.test_request_context(
        "/forms/translate/preview",
        method="POST",
        json={
            "text": "hello",
            "source_language": "en",
            "target_language": "hi",
        },
    ):
        response, status_code = _unwrap(preview_translation)()
        payload = response.get_json()

    assert status_code == 200
    assert payload["data"]["translated_text"] == "hello-hi"
