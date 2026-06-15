from services import llm_service as llm_service_module
from services.llm_service import LLMService


def test_scrub_pii_masks_email_phone_and_identifier():
    text = "Patient ID: ABC-123, call +1 555 123 4567 or alice@example.com"
    scrubbed = LLMService.scrub_pii(text)
    assert "[identifier]" in scrubbed
    assert "[phone]" in scrubbed
    assert "[email]" in scrubbed


def test_generate_form_scrubs_prompt_before_delegating(monkeypatch):
    captured = {}

    def fake_generate_form(prompt, current_form=None):
        captured["prompt"] = prompt
        captured["current_form"] = current_form
        return {"prompt": prompt, "current_form": current_form}

    monkeypatch.setattr(llm_service_module.AIService, "generate_form", fake_generate_form)

    result = LLMService.generate_form(
        "Patient ID: ABC-123, call alice@example.com",
        {"title": "Example"},
    )

    assert "[identifier]" in captured["prompt"]
    assert "[email]" in captured["prompt"]
    assert result["current_form"] == {"title": "Example"}
