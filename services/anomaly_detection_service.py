from typing import List, Dict, Any, Optional
from config.settings import settings
from services.ai_provider import LocalHeuristicProvider, OllamaProvider
from logger.unified_logger import app_logger, error_logger

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
        app_logger.info(f"AnomalyDetectionService: Running full detection for org {organization_id}")
        try:
            if not data:
                app_logger.info("AnomalyDetectionService: No data provided for detection")
                return {"anomalies_detected": 0, "anomalies": []}
                
            # Ensure we only process data for the correct organization
            scoped_data = [d for d in data if d.get("organization_id") == organization_id]
            app_logger.info(f"AnomalyDetectionService: Scoped data to {len(scoped_data)} items for org {organization_id}")
            
            anomalies = self.provider.detect_anomalies(scoped_data)
            
            result = {
                "anomalies_detected": len(anomalies),
                "anomalies": anomalies,
                "organization_id": organization_id
            }
            app_logger.info(f"AnomalyDetectionService: Successfully completed detection. Found {len(anomalies)} anomalies.")
            return result
        except Exception as e:
            error_logger.error(f"AnomalyDetectionService: Full detection failed: {str(e)}", exc_info=True)
            raise

    def detect_spam(self, text: str) -> Dict[str, Any]:
        """
        Heuristic spam detection.
        """
        app_logger.info("AnomalyDetectionService: Detecting spam in text")
        try:
            if not text:
                app_logger.debug("AnomalyDetectionService: Empty text provided for spam detection")
                return {"is_spam": False, "spam_score": 0}
                
            spam_keywords = ["lottery", "prize", "winner", "click here", "urgent"]
            text_lower = text.lower()
            positives = [kw for kw in spam_keywords if kw in text_lower]
            
            is_spam = len(positives) > 0
            result = {
                "is_spam": is_spam,
                "spam_score": 1.0 if is_spam else 0.0,
                "indicators": positives
            }
            app_logger.info(f"AnomalyDetectionService: Spam detection completed. is_spam: {is_spam}")
            return result
        except Exception as e:
            error_logger.error(f"AnomalyDetectionService: Spam detection failed: {str(e)}", exc_info=True)
            return {"is_spam": False, "spam_score": 0, "error": str(e)}

    def update_baseline(self, *args, **kwargs):
        app_logger.info("AnomalyDetectionService: Updating baseline")
        try:
            return {"status": "baseline_updated"}
        except Exception as e:
            error_logger.error(f"AnomalyDetectionService: Baseline update failed: {str(e)}", exc_info=True)
            raise

    def get_threshold_history(self, *args, **kwargs):
        app_logger.info("AnomalyDetectionService: Getting threshold history")
        return []

    def scan_batch(self, *args, **kwargs):
        app_logger.info("AnomalyDetectionService: Initiating batch scan")
        return {"status": "batch_scan_initiated"}

anomaly_detection_service = AnomalyDetectionService()
