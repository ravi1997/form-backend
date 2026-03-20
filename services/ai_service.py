from services.ai_provider import LocalHeuristicProvider, OllamaProvider
from config.settings import settings
from logger import get_logger

logger = get_logger(__name__)

class AIService:
    @property
    def provider(self):
        """Lazy-loaded AI provider based on configuration."""
        if settings.AI_PROVIDER == "ollama":
            return OllamaProvider(base_url=settings.OLLAMA_BASE_URL)
        return LocalHeuristicProvider()

    def generate_form(self, prompt, current_form=None):
        logger.info(f"Generating form from prompt: {prompt[:50]}...")
        # Sanitize before sending to provider (defense in depth)
        safe_prompt = self.provider.sanitize_prompt(prompt)
        return self.provider.summarize(safe_prompt) # Stub placeholder for form gen

    def get_suggestions(self, current_form):
        return self.provider.detect_anomalies([current_form])

    def analyze_form(self, form_data):
        return self.provider.classify_sentiment(str(form_data))

    def translate_text(self, text, source_lang, target_lang):
        # Implementation depends on provider capabilities
        return text

    def translate_bulk(self, items, source_lang, target_lang):
        return [self.translate_text(item, source_lang, target_lang) for item in items]

    def generate_embeddings(self, text: str) -> list[float]:
        """Vectorizes text using the active AI provider."""
        return self.provider.generate_embeddings(text)

ai_service = AIService()
