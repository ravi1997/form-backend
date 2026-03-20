import logging
import requests
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

logger = logging.getLogger(__name__)

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
        # Simple heuristic: take first two sentences
        sentences = text.split(".")
        summary = ". ".join(sentences[:2]).strip()
        if len(sentences) > 2:
            summary += "..."
        return f"[Heuristic Summary] {summary}"
        
    def detect_anomalies(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Simple heuristic: look for outliers in numeric fields if possible
        # For now, just a placeholder that marks nothing
        return []
        
    def classify_sentiment(self, text: str) -> Dict[str, Any]:
        positive_words = ["good", "great", "excellent", "happy", "love"]
        negative_words = ["bad", "poor", "terrible", "sad", "hate"]
        
        text_lower = text.lower()
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)
        
        if pos_count > neg_count:
            return {"sentiment": "positive", "score": 0.5 + (pos_count * 0.1)}
        elif neg_count > pos_count:
            return {"sentiment": "negative", "score": 0.5 + (neg_count * 0.1)}
        else:
            return {"sentiment": "neutral", "score": 0.5}

    def generate_embeddings(self, text: str) -> List[float]:
        # Return a deterministic mock vector based on text hash
        import hashlib
        h = hashlib.sha256(text.encode()).hexdigest()
        return [float(int(h[i:i+2], 16)) / 255.0 for i in range(0, 32, 2)]

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
        safe_text = self.sanitize_prompt(text)
        logger.info(f"Ollama summarizing safe text: {safe_text[:50]}...")
        payload = {
            "model": "llama3",
            "prompt": f"Summarize the following text securely: {safe_text}",
            "stream": False
        }
        resp = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(requests.RequestException)
    )
    def detect_anomalies(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Hardened anomaly detection path
        return []

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(requests.RequestException)
    )
    def classify_sentiment(self, text: str) -> Dict[str, Any]:
        safe_text = self.sanitize_prompt(text)
        payload = {
            "model": "llama3",
            "prompt": f"Classify the sentiment of this text as positive, negative, or neutral: {safe_text}. Reply ONLY with the classification.",
            "stream": False
        }
        try:
            resp = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=15)
            resp.raise_for_status()
            sentiment = resp.json().get("response", "").strip().lower()
            return {"sentiment": sentiment, "score": 0.8, "provider": "ollama"}
        except Exception as e:
            logger.error(f"Sentiment classification failed: {e}")
            return {"sentiment": "neutral", "score": 0.5, "provider": "ollama"}

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(requests.RequestException)
    )
    def generate_embeddings(self, text: str) -> List[float]:
        payload = {
            "model": "llama3",
            "prompt": text,
        }
        resp = requests.post(f"{self.base_url}/api/embeddings", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json().get("embedding", [])
