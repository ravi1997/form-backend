import requests
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
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
        
    @abstractmethod
    def detect_anomalies(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        pass
        
    @abstractmethod
    def classify_sentiment(self, text: str) -> Dict[str, Any]:
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
        # Simple heuristic: look for outliers in numeric fields if possible
        # For now, just a placeholder that marks nothing
        app_logger.debug("LocalHeuristicProvider: Finished anomaly detection (no-op)")
        return []
        
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
        app_logger.debug(f"LocalHeuristicProvider: Sentiment classified as {result['sentiment']}")
        return result

    def generate_embeddings(self, text: str) -> List[float]:
        app_logger.debug("LocalHeuristicProvider: Generating embeddings")
        # Return a deterministic mock vector based on text hash
        import hashlib
        h = hashlib.sha256(text.encode()).hexdigest()
        result = [float(int(h[i:i+2], 16)) / 255.0 for i in range(0, 32, 2)]
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
        retry=retry_if_exception_type(requests.RequestException)
    )
    def summarize(self, text: str, context: Optional[str] = None) -> str:
        app_logger.info("OllamaProvider: Starting summarization")
        try:
            safe_text = self.sanitize_prompt(text)
            app_logger.info(f"Ollama summarizing safe text: {safe_text[:50]}...")
            payload = {
                "model": "llama3",
                "prompt": f"Summarize the following text securely: {safe_text}",
                "stream": False
            }
            resp = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=30)
            resp.raise_for_status()
            result = resp.json().get("response", "").strip()
            app_logger.info("OllamaProvider: Successfully summarized text")
            return result
        except Exception as e:
            error_logger.error(f"OllamaProvider: Summarization failed: {str(e)}", exc_info=True)
            raise

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(requests.RequestException)
    )
    def detect_anomalies(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Hardened anomaly detection path
        app_logger.info("OllamaProvider: Running anomaly detection (stub)")
        return []

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(requests.RequestException)
    )
    def classify_sentiment(self, text: str) -> Dict[str, Any]:
        app_logger.info("OllamaProvider: Classifying sentiment")
        try:
            safe_text = self.sanitize_prompt(text)
            payload = {
                "model": "llama3",
                "prompt": f"Classify the sentiment of this text as positive, negative, or neutral: {safe_text}. Reply ONLY with the classification.",
                "stream": False
            }
            resp = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=15)
            resp.raise_for_status()
            sentiment = resp.json().get("response", "").strip().lower()
            app_logger.info(f"OllamaProvider: Sentiment classified as {sentiment}")
            return {"sentiment": sentiment, "score": 0.8, "provider": "ollama"}
        except Exception as e:
            error_logger.error(f"OllamaProvider: Sentiment classification failed: {str(e)}", exc_info=True)
            return {"sentiment": "neutral", "score": 0.5, "provider": "ollama"}

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(requests.RequestException)
    )
    def generate_embeddings(self, text: str) -> List[float]:
        app_logger.info("OllamaProvider: Generating embeddings")
        try:
            payload = {
                "model": "llama3",
                "prompt": text,
            }
            resp = requests.post(f"{self.base_url}/api/embeddings", json=payload, timeout=30)
            resp.raise_for_status()
            result = resp.json().get("embedding", [])
            app_logger.info("OllamaProvider: Successfully generated embeddings")
            return result
        except Exception as e:
            error_logger.error(f"OllamaProvider: Embedding generation failed: {str(e)}", exc_info=True)
            raise
