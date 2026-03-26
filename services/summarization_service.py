from typing import List, Dict, Any, Optional
from config.settings import settings
from services.ai_provider import LocalHeuristicProvider, OllamaProvider
from logger.unified_logger import app_logger, error_logger

class SummarizationService:
    def __init__(self):
        # Initialize provider based on settings
        try:
            if settings.AI_PROVIDER == "ollama":
                self.provider = OllamaProvider(base_url=settings.OLLAMA_BASE_URL)
            else:
                self.provider = LocalHeuristicProvider()
            app_logger.info(f"SummarizationService initialized with {settings.AI_PROVIDER} provider")
        except Exception as e:
            error_logger.error(f"Failed to initialize SummarizationService: {e}", exc_info=True)
            raise

    def hybrid_summarize(self, text: str, context: Optional[str] = None) -> str:
        """
        Summarize text using the configured AI provider.
        """
        app_logger.info(f"Summarizing text with context: {context}")
        if not text:
            app_logger.debug("Empty text provided for summarization")
            return ""
        try:
            summary = self.provider.summarize(text, context=context)
            app_logger.info("Text summarization completed successfully")
            return summary
        except Exception as e:
            error_logger.error(f"Error in hybrid_summarize: {e}", exc_info=True)
            return ""

    def save_summary_snapshot(self, *args, **kwargs):
        app_logger.info("Saving summary snapshot (stub)")
        return "stub_snapshot_id"

    def generate_executive_summary(self, responses: List[Dict[str, Any]], chunk_size: int = 50) -> str:
        """
        Aggregates multiple responses into a single executive summary using Map-Reduce.
        """
        app_logger.info(f"Generating executive summary for {len(responses)} responses")
        if not responses:
            app_logger.warning("No data to summarize for executive summary")
            return "No data to summarize."
            
        try:
            # 1. Map Phase: Summarize each chunk
            chunk_summaries = []
            for i in range(0, len(responses), chunk_size):
                app_logger.debug(f"Processing chunk starting at index {i}")
                chunk = responses[i : i + chunk_size]
                combined_text = "\n".join([str(r.get("data", "")) for r in chunk])
                # Sanitize before sending to provider
                safe_text = self.provider.sanitize_prompt(combined_text)
                summary = self.provider.summarize(safe_text, context=f"Chunk {i//chunk_size} Summary")
                chunk_summaries.append(summary)
                
            # 2. Reduce Phase: Summarize the summaries
            if len(chunk_summaries) == 1:
                app_logger.info("Single chunk summary completed")
                return chunk_summaries[0]
                
            app_logger.info(f"Reducing {len(chunk_summaries)} chunk summaries into final executive summary")
            final_input_text = "\n---\n".join(chunk_summaries)
            # Final summarization to produce executive overview
            result = self.provider.summarize(final_input_text, context="Final Executive Reduction")
            app_logger.info("Executive summary generation completed")
            return result
        except Exception as e:
            error_logger.error(f"Error generating executive summary: {e}", exc_info=True)
            return "Error generating executive summary."

    def _analyze_themes(self, *args, **kwargs):
        return {}

    def compare_summaries(self, text_a: str, text_b: str) -> Dict[str, Any]:
        """
        Compare two summaries.
        """
        app_logger.info("Comparing summaries")
        return {
            "comparison": "Similarity analysis not yet implemented in provider.",
            "provider": settings.AI_PROVIDER
        }

    def get_summary_trends(self, *args, **kwargs):
        return []

    def invalidate_cache(self, *args, **kwargs):
        app_logger.info("Invalidating summarization cache")
        return True

summarization_service = SummarizationService()
