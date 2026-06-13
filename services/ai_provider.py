import requests
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from tenacity import (
    retry,
    wait_exponential,
    stop_after_attempt,
    retry_if_exception_type,
)
from logger.unified_logger import app_logger, error_logger


class BaseAIProvider(ABC):
    """
    Abstract Base Class for AI Providers.
    Ensures a consistent interface for Summarization and Anomaly Detection.
    """

    @abstractmethod
    def summarize(self, text: str, context: Optional[str] = None) -> str:
        pass

    def sanitize_prompt(self, text: str) -> str:
        """
        Removes PII and sensitive data from text before sending to LLM.
        """
        from utils.pii_sanitizer import sanitize_text

        return sanitize_text(text)

    def _heuristic_anomaly_scan(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        anomalies: List[Dict[str, Any]] = []
        suspicious_values = {"", "n/a", "na", "none", "null", "test", "sample"}

        for index, record in enumerate(data):
            if not isinstance(record, dict):
                anomalies.append(
                    {
                        "index": index,
                        "issue": "non_object_record",
                        "severity": "low",
                    }
                )
                continue

            record_issues = []
            for key, value in record.items():
                if value is None:
                    record_issues.append({"field": key, "issue": "null_value"})
                    continue
                if isinstance(value, str) and value.strip().lower() in suspicious_values:
                    record_issues.append({"field": key, "issue": "suspicious_placeholder"})
                if isinstance(value, (int, float)) and value < 0:
                    record_issues.append({"field": key, "issue": "negative_numeric_value"})

            if record_issues:
                anomalies.append(
                    {
                        "index": index,
                        "issues": record_issues,
                        "severity": "medium" if len(record_issues) > 1 else "low",
                    }
                )

        return anomalies

    @abstractmethod
    def detect_anomalies(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def classify_sentiment(self, text: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def classify_taxonomy(
        self, text: str, taxonomy: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def generate_embeddings(self, text: str) -> List[float]:
        pass


class LocalHeuristicProvider(BaseAIProvider):
    """
    Implementation using local heuristics (Regex, Word lists).
    Used as an honest fallback when no LLM is configured.
    """

    def summarize(self, text: str, context: Optional[str] = None) -> str:
        app_logger.debug("LocalHeuristicProvider: Summarizing text")
        # Simple heuristic: take first two sentences
        sentences = text.split(".")
        summary = ". ".join(sentences[:2]).strip()
        if len(sentences) > 2:
            summary += "..."
        result = f"[Heuristic Summary] {summary}"
        app_logger.debug("LocalHeuristicProvider: Successfully summarized text")
        return result

    def detect_anomalies(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        app_logger.debug("LocalHeuristicProvider: Detecting anomalies")
        result = self._heuristic_anomaly_scan(data)
        app_logger.debug(
            f"LocalHeuristicProvider: Finished anomaly detection with {len(result)} findings"
        )
        return result

    def classify_sentiment(self, text: str) -> Dict[str, Any]:
        app_logger.debug("LocalHeuristicProvider: Classifying sentiment")
        positive_words = ["good", "great", "excellent", "happy", "love"]
        negative_words = ["bad", "poor", "terrible", "sad", "hate"]

        text_lower = text.lower()
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)

        if pos_count > neg_count:
            result = {"sentiment": "positive", "score": 0.5 + (pos_count * 0.1)}
        elif neg_count > pos_count:
            result = {"sentiment": "negative", "score": 0.5 + (neg_count * 0.1)}
        else:
            result = {"sentiment": "neutral", "score": 0.5}
        app_logger.debug(
            f"LocalHeuristicProvider: Sentiment classified as {result['sentiment']}"
        )
        return result

    def classify_taxonomy(
        self, text: str, taxonomy: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        app_logger.debug("LocalHeuristicProvider: Classifying taxonomy via heuristics")
        text_lower = text.lower()
        matched_tags = []
        scores = {}
        for item in taxonomy:
            cat = item.get("category_name")
            desc = item.get("description", "").lower()
            kws = item.get("keywords", [])
            match_count = 0
            # Match keywords
            for kw in kws:
                if kw.lower() in text_lower:
                    match_count += 2
            # Match category name
            if cat.lower() in text_lower:
                match_count += 3
            # Match description key terms
            for term in desc.split():
                if len(term) > 3 and term in text_lower:
                    match_count += 0.5
            if match_count > 0:
                matched_tags.append(cat)
                scores[cat] = min(1.0, match_count / 5.0)
        return {"tags": matched_tags, "scores": scores, "provider": "heuristic"}

    def generate_embeddings(self, text: str) -> List[float]:
        app_logger.debug("LocalHeuristicProvider: Generating embeddings")
        # Return a deterministic mock vector based on text hash
        import hashlib

        h = hashlib.sha256(text.encode()).hexdigest()
        result = [float(int(h[i : i + 2], 16)) / 255.0 for i in range(0, 32, 2)]
        app_logger.debug("LocalHeuristicProvider: Generated mock embeddings")
        return result


class OllamaProvider(BaseAIProvider):
    """
    Ollama (Local LLM) implementation.
    Requires external Ollama inference server.
    """

    def __init__(self, base_url="http://localhost:11434"):
        self.base_url = base_url

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def summarize(self, text: str, context: Optional[str] = None) -> str:
        app_logger.info("OllamaProvider: Starting summarization")
        try:
            safe_text = self.sanitize_prompt(text)
            app_logger.info(f"Ollama summarizing safe text: {safe_text[:50]}...")
            payload = {
                "model": "llama3",
                "prompt": f"Summarize the following text securely: {safe_text}",
                "stream": False,
            }
            resp = requests.post(
                f"{self.base_url}/api/generate", json=payload, timeout=30
            )
            resp.raise_for_status()
            result = resp.json().get("response", "").strip()
            app_logger.info("OllamaProvider: Successfully summarized text")
            return result
        except Exception as e:
            error_logger.error(
                f"OllamaProvider: Summarization failed: {str(e)}", exc_info=True
            )
            raise

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def detect_anomalies(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        app_logger.info("OllamaProvider: Running anomaly detection (heuristic fallback)")
        return self._heuristic_anomaly_scan(data)

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def classify_sentiment(self, text: str) -> Dict[str, Any]:
        app_logger.info("OllamaProvider: Classifying sentiment")
        try:
            safe_text = self.sanitize_prompt(text)
            payload = {
                "model": "llama3",
                "prompt": f"Classify the sentiment of this text as positive, negative, or neutral: {safe_text}. Reply ONLY with the classification.",
                "stream": False,
            }
            resp = requests.post(
                f"{self.base_url}/api/generate", json=payload, timeout=15
            )
            resp.raise_for_status()
            sentiment = resp.json().get("response", "").strip().lower()
            app_logger.info(f"OllamaProvider: Sentiment classified as {sentiment}")
            return {"sentiment": sentiment, "score": 0.8, "provider": "ollama"}
        except Exception as e:
            error_logger.error(
                f"OllamaProvider: Sentiment classification failed: {str(e)}",
                exc_info=True,
            )
            return {"sentiment": "neutral", "score": 0.5, "provider": "ollama"}

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def classify_taxonomy(
        self, text: str, taxonomy: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        app_logger.info("OllamaProvider: Classifying text against taxonomy")
        try:
            safe_text = self.sanitize_prompt(text)
            tax_desc = []
            valid_categories = []
            for item in taxonomy:
                cat = item.get("category_name")
                desc = item.get("description", "")
                kws = ", ".join(item.get("keywords", []))
                tax_desc.append(
                    f"- Category: {cat}\n  Description: {desc}\n  Keywords: {kws}"
                )
                valid_categories.append(cat.lower())

            taxonomy_str = "\n".join(tax_desc)
            categories_str = ", ".join(valid_categories)

            prompt = (
                f"Analyze the following response text and match it against the taxonomy below.\n\n"
                f'Response Text:\n"""\n{safe_text}\n"""\n\n'
                f"Available Taxonomy:\n{taxonomy_str}\n\n"
                f"Instructions:\n"
                f"Output a comma-separated list containing ONLY the category names that match the text. "
                f"Valid categories to pick from: [{categories_str}]. "
                f"If none of them match, output 'none'. "
                f"Do NOT output any markdown, explanations, or introductory text. Just the comma-separated list."
            )

            payload = {
                "model": "llama3",
                "prompt": prompt,
                "stream": False,
            }
            resp = requests.post(
                f"{self.base_url}/api/generate", json=payload, timeout=20
            )
            resp.raise_for_status()
            raw_response = resp.json().get("response", "").strip()

            matched_tags = []
            scores = {}
            if raw_response.lower() != "none" and raw_response:
                # Parse comma separated tags
                candidates = [c.strip().lower() for c in raw_response.split(",")]
                for item in taxonomy:
                    cat = item.get("category_name")
                    if cat.lower() in candidates:
                        matched_tags.append(cat)
                        scores[cat] = (
                            0.9  # Default confidence score for model classifications
                        )

            app_logger.info(f"OllamaProvider: Matched tags: {matched_tags}")
            return {"tags": matched_tags, "scores": scores, "provider": "ollama"}
        except Exception as e:
            error_logger.error(
                f"OllamaProvider: Taxonomy classification failed: {str(e)}",
                exc_info=True,
            )
            # Fallback to local heuristic classifier if HTTP/Ollama fails
            fallback = LocalHeuristicProvider()
            return fallback.classify_taxonomy(text, taxonomy)

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def generate_embeddings(self, text: str) -> List[float]:
        app_logger.info("OllamaProvider: Generating embeddings")
        try:
            payload = {
                "model": "llama3",
                "prompt": text,
            }
            resp = requests.post(
                f"{self.base_url}/api/embeddings", json=payload, timeout=30
            )
            resp.raise_for_status()
            result = resp.json().get("embedding", [])
            app_logger.info("OllamaProvider: Successfully generated embeddings")
            return result
        except Exception as e:
            error_logger.error(
                f"OllamaProvider: Embedding generation failed: {str(e)}", exc_info=True
            )
            raise
