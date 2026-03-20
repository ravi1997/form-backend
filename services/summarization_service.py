from typing import List, Dict, Any, Optional
from config.settings import settings
from services.ai_provider import LocalHeuristicProvider, OllamaProvider

class SummarizationService:
    def __init__(self):
        # Initialize provider based on settings
        if settings.AI_PROVIDER == "ollama":
            self.provider = OllamaProvider(base_url=settings.OLLAMA_BASE_URL)
        else:
            self.provider = LocalHeuristicProvider()

    def hybrid_summarize(self, text: str, context: Optional[str] = None) -> str:
        """
        Summarize text using the configured AI provider.
        """
        if not text:
            return ""
        return self.provider.summarize(text, context=context)

    def save_summary_snapshot(self, *args, **kwargs):
        return "stub_snapshot_id"

    def generate_executive_summary(self, responses: List[Dict[str, Any]], chunk_size: int = 50) -> str:
        """
        Aggregates multiple responses into a single executive summary using Map-Reduce.
        """
        if not responses:
            return "No data to summarize."
            
        # 1. Map Phase: Summarize each chunk
        chunk_summaries = []
        for i in range(0, len(responses), chunk_size):
            chunk = responses[i : i + chunk_size]
            combined_text = "\n".join([str(r.get("data", "")) for r in chunk])
            # Sanitize before sending to provider
            safe_text = self.provider.sanitize_prompt(combined_text)
            summary = self.provider.summarize(safe_text, context=f"Chunk {i//chunk_size} Summary")
            chunk_summaries.append(summary)
            
        # 2. Reduce Phase: Summarize the summaries
        if len(chunk_summaries) == 1:
            return chunk_summaries[0]
            
        final_input_text = "\n---\n".join(chunk_summaries)
        # Final summarization to produce executive overview
        return self.provider.summarize(final_input_text, context="Final Executive Reduction")

    def _analyze_themes(self, *args, **kwargs):
        return {}

    def compare_summaries(self, text_a: str, text_b: str) -> Dict[str, Any]:
        """
        Compare two summaries.
        """
        return {
            "comparison": "Similarity analysis not yet implemented in provider.",
            "provider": settings.AI_PROVIDER
        }

    def get_summary_trends(self, *args, **kwargs):
        return []

    def invalidate_cache(self, *args, **kwargs):
        return True

summarization_service = SummarizationService()
