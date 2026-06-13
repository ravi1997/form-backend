import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from config.settings import settings
from models import FormResponse
from models.Response import SummarySnapshot
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
            app_logger.info(
                f"SummarizationService initialized with {settings.AI_PROVIDER} provider"
            )
        except Exception as e:
            error_logger.error(
                f"Failed to initialize SummarizationService: {e}", exc_info=True
            )
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

    def summarize_form(
        self, form_id: str, response_ids: Optional[List[str]] = None
    ) -> str:
        """Summarize all or selected responses for a form."""
        app_logger.info(f"Summarizing form {form_id}")
        query = FormResponse.objects(form=form_id, is_deleted=False)
        if response_ids:
            query = query(id__in=response_ids)
        responses = list(query)
        if len(responses) < 2:
            raise ValueError("At least 2 responses required for summarization")

        response_payloads = []
        timestamps = []

        def extract_text(obj: Any, texts: List[str]) -> None:
            if isinstance(obj, dict):
                for value in obj.values():
                    extract_text(value, texts)
            elif isinstance(obj, list):
                for item in obj:
                    extract_text(item, texts)
            elif isinstance(obj, str) and obj.strip():
                texts.append(obj.strip())

        for response in responses:
            payload = (
                response.get_decrypted_data()
                if hasattr(response, "get_decrypted_data")
                else getattr(response, "data", {})
            )
            texts: List[str] = []
            extract_text(payload, texts)
            combined = " ".join(texts).strip()
            if not combined:
                continue
            response_payloads.append(
                {
                    "response_id": str(getattr(response, "id", "")),
                    "data": combined,
                }
            )
            submitted_at = getattr(response, "submitted_at", None)
            if submitted_at is not None:
                timestamps.append(submitted_at)

        if len(response_payloads) < 2:
            raise ValueError("At least 2 responses required for summarization")

        summary = self.generate_executive_summary(response_payloads)
        period_start = min(timestamps) if timestamps else datetime.now(timezone.utc)
        period_end = max(timestamps) if timestamps else datetime.now(timezone.utc)
        try:
            self.save_summary_snapshot(
                form_id=form_id,
                period_start=period_start,
                period_end=period_end,
                summary_data={
                    "summary": summary,
                    "response_ids": [item["response_id"] for item in response_payloads],
                },
                response_count=len(response_payloads),
                strategy_used="generate_executive_summary",
            )
        except Exception as exc:
            error_logger.warning(
                f"Failed to persist summary snapshot for form {form_id}: {exc}"
            )
        return summary

    def save_summary_snapshot(
        self,
        *,
        form_id: str,
        period_start: datetime,
        period_end: datetime,
        summary_data: Dict[str, Any],
        created_by: Optional[str] = None,
        period_label: Optional[str] = None,
        response_count: int = 0,
        strategy_used: Optional[str] = None,
    ) -> str:
        """Persist a snapshot of an AI-generated summary."""
        app_logger.info(
            f"Saving summary snapshot for form {form_id} ({period_start} -> {period_end})"
        )
        snapshot = SummarySnapshot(
            form_id=str(form_id),
            period_start=period_start,
            period_end=period_end,
            period_label=period_label,
            response_count=response_count,
            strategy_used=strategy_used or settings.AI_PROVIDER,
            summary_data=summary_data,
            created_by=created_by,
            timestamp=datetime.now(timezone.utc),
        )
        snapshot.save()
        return str(snapshot.id)

    def generate_executive_summary(
        self, responses: List[Dict[str, Any]], chunk_size: int = 50
    ) -> str:
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
                summary = self.provider.summarize(
                    safe_text, context=f"Chunk {i//chunk_size} Summary"
                )
                chunk_summaries.append(summary)

            # 2. Reduce Phase: Summarize the summaries
            if len(chunk_summaries) == 1:
                app_logger.info("Single chunk summary completed")
                return chunk_summaries[0]

            app_logger.info(
                f"Reducing {len(chunk_summaries)} chunk summaries into final executive summary"
            )
            final_input_text = "\n---\n".join(chunk_summaries)
            # Final summarization to produce executive overview
            result = self.provider.summarize(
                final_input_text, context="Final Executive Reduction"
            )
            app_logger.info("Executive summary generation completed")
            return result
        except Exception as e:
            error_logger.error(
                f"Error generating executive summary: {e}", exc_info=True
            )
            return "Error generating executive summary."

    def _analyze_themes(self, *args, **kwargs):
        return {}

    def compare_summaries(self, text_a: str, text_b: str) -> Dict[str, Any]:
        """
        Compare two summaries.
        """
        app_logger.info("Comparing summaries")
        a_tokens = {
            token
            for token in re.findall(r"[a-z0-9]+", (text_a or "").lower())
            if token
        }
        b_tokens = {
            token
            for token in re.findall(r"[a-z0-9]+", (text_b or "").lower())
            if token
        }
        overlap = sorted(a_tokens & b_tokens)
        union = a_tokens | b_tokens
        score = round((len(overlap) / len(union)) if union else 1.0, 3)
        changes = sorted((a_tokens ^ b_tokens))
        return {
            "comparison": {
                "score": score,
                "overlap_terms": overlap,
                "changed_terms": changes,
            },
            "provider": settings.AI_PROVIDER,
        }

    def get_summary_trends(self, *args, **kwargs):
        return []

    def invalidate_cache(self, *args, **kwargs):
        app_logger.info("Invalidating summarization cache")
        return True


summarization_service = SummarizationService()
