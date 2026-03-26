from services.ai_provider import LocalHeuristicProvider, OllamaProvider
from config.settings import settings
from logger.unified_logger import app_logger, error_logger

class AIService:
    @property
    def provider(self):
        """Lazy-loaded AI provider based on configuration."""
        if settings.AI_PROVIDER == "ollama":
            return OllamaProvider(base_url=settings.OLLAMA_BASE_URL)
        return LocalHeuristicProvider()

    def generate_form(self, prompt, current_form=None):
        app_logger.info(f"AIService: Generating form from prompt: {prompt[:50]}...")
        try:
            # Sanitize before sending to provider (defense in depth)
            safe_prompt = self.provider.sanitize_prompt(prompt)
            result = self.provider.summarize(safe_prompt) # Stub placeholder for form gen
            app_logger.info("AIService: Successfully generated form")
            return result
        except Exception as e:
            error_logger.error(f"AIService: Form generation failed: {str(e)}", exc_info=True)
            raise

    def get_suggestions(self, current_form):
        app_logger.info("AIService: Getting suggestions for form")
        try:
            result = self.provider.detect_anomalies([current_form])
            app_logger.info("AIService: Successfully retrieved suggestions")
            return result
        except Exception as e:
            error_logger.error(f"AIService: Failed to get suggestions: {str(e)}", exc_info=True)
            raise

    def analyze_form(self, form_data):
        app_logger.info("AIService: Analyzing form data")
        try:
            result = self.provider.classify_sentiment(str(form_data))
            app_logger.info("AIService: Successfully analyzed form")
            return result
        except Exception as e:
            error_logger.error(f"AIService: Form analysis failed: {str(e)}", exc_info=True)
            raise

    def translate_text(self, text, source_lang, target_lang):
        app_logger.info(f"AIService: Translating text from {source_lang} to {target_lang}")
        try:
            # Implementation depends on provider capabilities
            app_logger.info("AIService: Translation completed (stub)")
            return text
        except Exception as e:
            error_logger.error(f"AIService: Translation failed: {str(e)}", exc_info=True)
            raise

    def translate_bulk(self, items, source_lang, target_lang):
        app_logger.info(f"AIService: Translating {len(items)} items from {source_lang} to {target_lang}")
        try:
            result = [self.translate_text(item, source_lang, target_lang) for item in items]
            app_logger.info("AIService: Bulk translation completed")
            return result
        except Exception as e:
            error_logger.error(f"AIService: Bulk translation failed: {str(e)}", exc_info=True)
            raise

    def generate_embeddings(self, text: str) -> list[float]:
        """Vectorizes text using the active AI provider."""
        app_logger.info("AIService: Generating embeddings for text")
        try:
            result = self.provider.generate_embeddings(text)
            app_logger.info("AIService: Successfully generated embeddings")
            return result
        except Exception as e:
            error_logger.error(f"AIService: Embedding generation failed: {str(e)}", exc_info=True)
            raise

ai_service = AIService()
