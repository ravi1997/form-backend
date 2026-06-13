import requests
import re

from services.ai_provider import LocalHeuristicProvider, OllamaProvider
from config.settings import settings
from logger.unified_logger import app_logger, error_logger
from typing import Any


class AIService:
    _TRANSLATION_GLOSSARY = {
        "es": {
            "hello": "hola",
            "hi": "hola",
            "thank you": "gracias",
            "form": "formulario",
            "name": "nombre",
            "date": "fecha",
            "submit": "enviar",
            "save": "guardar",
            "response": "respuesta",
        },
        "fr": {
            "hello": "bonjour",
            "hi": "salut",
            "thank you": "merci",
            "form": "formulaire",
            "name": "nom",
            "date": "date",
            "submit": "soumettre",
            "save": "enregistrer",
            "response": "réponse",
        },
        "hi": {
            "hello": "नमस्ते",
            "hi": "नमस्ते",
            "thank you": "धन्यवाद",
            "form": "फॉर्म",
            "name": "नाम",
            "date": "तारीख",
            "submit": "जमा करें",
            "save": "सहेजें",
            "response": "उत्तर",
        },
    }

    @classmethod
    def provider(cls):
        """Lazy-loaded AI provider based on configuration."""
        if settings.AI_PROVIDER == "ollama":
            return OllamaProvider(base_url=settings.OLLAMA_BASE_URL)
        return LocalHeuristicProvider()

    @classmethod
    def generate_form(cls, prompt, current_form=None):
        app_logger.info(f"AIService: Generating form from prompt: {prompt[:50]}...")
        try:
            # Sanitize before sending to provider (defense in depth)
            safe_prompt = cls.provider().sanitize_prompt(prompt)
            summary = cls.provider().summarize(safe_prompt)
            result = {
                "prompt": prompt,
                "summary": summary,
                "current_form": current_form or {},
            }
            app_logger.info("AIService: Successfully generated form")
            return result
        except Exception as e:
            error_logger.error(
                f"AIService: Form generation failed: {str(e)}", exc_info=True
            )
            raise

    @classmethod
    def get_suggestions(cls, current_form):
        app_logger.info("AIService: Getting suggestions for form")
        try:
            result = cls.provider().detect_anomalies([current_form])
            app_logger.info("AIService: Successfully retrieved suggestions")
            return result
        except Exception as e:
            error_logger.error(
                f"AIService: Failed to get suggestions: {str(e)}", exc_info=True
            )
            raise

    @classmethod
    def analyze_form(cls, form_data):
        app_logger.info("AIService: Analyzing form data")
        try:
            result = cls.provider().classify_sentiment(str(form_data))
            app_logger.info("AIService: Successfully analyzed form")
            return result
        except Exception as e:
            error_logger.error(
                f"AIService: Form analysis failed: {str(e)}", exc_info=True
            )
            raise

    @classmethod
    def translate_text(cls, text, source_lang, target_lang):
        app_logger.info(
            f"AIService: Translating text from {source_lang} to {target_lang}"
        )
        try:
            provider = cls.provider()
            if isinstance(provider, OllamaProvider):
                safe_text = provider.sanitize_prompt(text)
                payload = {
                    "model": "llama3",
                    "prompt": (
                        f"Translate the following text from {source_lang} to {target_lang}. "
                        f"Return only the translated text.\n\nText:\n{safe_text}"
                    ),
                    "stream": False,
                }
                resp = requests.post(
                    f"{provider.base_url}/api/generate", json=payload, timeout=30
                )
                resp.raise_for_status()
                translated = resp.json().get("response", "").strip()
                app_logger.info("AIService: Translation completed via Ollama")
                return translated or text

            translated = cls._heuristic_translate_text(text, target_lang)
            app_logger.info("AIService: Translation completed using heuristic fallback")
            return translated
        except Exception as e:
            error_logger.error(
                f"AIService: Translation failed: {str(e)}", exc_info=True
            )
            raise

    @classmethod
    def translate_bulk(cls, items, source_lang, target_lang):
        app_logger.info(
            f"AIService: Translating {len(items)} items from {source_lang} to {target_lang}"
        )
        try:
            result = [cls.translate_text(item, source_lang, target_lang) for item in items]
            app_logger.info("AIService: Bulk translation completed")
            return result
        except Exception as e:
            error_logger.error(
                f"AIService: Bulk translation failed: {str(e)}", exc_info=True
            )
            raise

    @classmethod
    def classify_taxonomy(
        cls, text: str, taxonomy: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Classify text against predefined taxonomy using active provider."""
        app_logger.info("AIService: Classifying text against taxonomy")
        try:
            result = cls.provider().classify_taxonomy(text, taxonomy)
            app_logger.info("AIService: Successfully completed taxonomy classification")
            return result
        except Exception as e:
            error_logger.error(
                f"AIService: Taxonomy classification failed: {str(e)}", exc_info=True
            )
            raise

    @classmethod
    def generate_embeddings(cls, text: str) -> list[float]:
        """Vectorizes text using the active AI provider."""
        app_logger.info("AIService: Generating embeddings for text")
        try:
            result = cls.provider().generate_embeddings(text)
            app_logger.info("AIService: Successfully generated embeddings")
            return result
        except Exception as e:
            error_logger.error(
                f"AIService: Embedding generation failed: {str(e)}", exc_info=True
            )
            raise

    @classmethod
    def _heuristic_translate_text(cls, text: str, target_lang: str) -> str:
        lang_key = (target_lang or "").strip().lower().split("-")[0]
        glossary = cls._TRANSLATION_GLOSSARY.get(lang_key)
        if not glossary:
            return text

        translated = text
        for source, target in sorted(glossary.items(), key=lambda item: len(item[0]), reverse=True):
            pattern = re.compile(rf"\b{re.escape(source)}\b", re.IGNORECASE)
            translated = pattern.sub(target, translated)

        if translated == text:
            return f"[{lang_key}] {text}"
        return translated


from typing import Any

ai_service = AIService()
