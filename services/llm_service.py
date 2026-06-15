from __future__ import annotations

import re
from typing import Any

from logger.unified_logger import app_logger
from services.ai_service import AIService


class LLMService:
    """Unified LLM façade with lightweight PII scrubbing."""

    EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    PHONE_RE = re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b")
    ID_RE = re.compile(r"\b(?:MRN|PID|Patient ID|patient id)\s*[:#-]?\s*[\w-]+\b", re.I)

    @classmethod
    def scrub_pii(cls, text: str) -> str:
        if not text:
            return text
        scrubbed = cls.EMAIL_RE.sub("[email]", text)
        scrubbed = cls.PHONE_RE.sub("[phone]", scrubbed)
        scrubbed = cls.ID_RE.sub("[identifier]", scrubbed)
        return scrubbed

    @classmethod
    def generate_form(cls, prompt: str, current_form: dict[str, Any] | None = None):
        app_logger.info("LLMService: generating form from prompt")
        safe_prompt = cls.scrub_pii(prompt)
        safe_form = current_form or {}
        return AIService.generate_form(safe_prompt, safe_form)

    @classmethod
    def generate_text(cls, prompt: str, context: str | None = None):
        app_logger.info("LLMService: generating text from prompt")
        safe_prompt = cls.scrub_pii(prompt)
        safe_context = cls.scrub_pii(context) if context else None
        provider = AIService.provider()
        if safe_context:
            return provider.summarize(safe_prompt, safe_context)
        return provider.summarize(safe_prompt)

    @classmethod
    def suggest_for_form(cls, current_form: dict[str, Any]):
        return AIService.get_suggestions(current_form)

    @classmethod
    def validate_form(cls, form_data: dict[str, Any]):
        return AIService.analyze_form(form_data)
