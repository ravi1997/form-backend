from typing import List, Dict, Any, Optional
from config.settings import settings
from services.ai_provider import LocalHeuristicProvider, OllamaProvider

class AnomalyDetectionService:
    def __init__(self):
        # Initialize provider based on settings
        if settings.AI_PROVIDER == "ollama":
            self.provider = OllamaProvider(base_url=settings.OLLAMA_BASE_URL)
        else:
            self.provider = LocalHeuristicProvider()

    def run_full_detection(self, data: List[Dict[str, Any]], organization_id: str) -> Dict[str, Any]:
        """
        Run anomaly detection on responses for a specific organization.
        """
        if not data:
            return {"anomalies_detected": 0, "anomalies": []}
            
        # Ensure we only process data for the correct organization
        scoped_data = [d for d in data if d.get("organization_id") == organization_id]
        anomalies = self.provider.detect_anomalies(scoped_data)
        
        return {
            "anomalies_detected": len(anomalies),
            "anomalies": anomalies,
            "organization_id": organization_id
        }

    def detect_spam(self, text: str) -> Dict[str, Any]:
        """
        Heuristic spam detection.
        """
        if not text:
            return {"is_spam": False, "spam_score": 0}
            
        spam_keywords = ["lottery", "prize", "winner", "click here", "urgent"]
        text_lower = text.lower()
        positives = [kw for kw in spam_keywords if kw in text_lower]
        
        is_spam = len(positives) > 0
        return {
            "is_spam": is_spam,
            "spam_score": 1.0 if is_spam else 0.0,
            "indicators": positives
        }

    def update_baseline(self, *args, **kwargs):
        return {"status": "baseline_updated"}

    def get_threshold_history(self, *args, **kwargs):
        return []

    def scan_batch(self, *args, **kwargs):
        return {"status": "batch_scan_initiated"}

anomaly_detection_service = AnomalyDetectionService()
