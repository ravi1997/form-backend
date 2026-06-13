from typing import List, Dict, Any, Optional
from config.settings import settings
from services.ai_provider import LocalHeuristicProvider, OllamaProvider
from logger.unified_logger import app_logger, error_logger
from models import AnomalyThreshold, Form


class AnomalyDetectionService:
    def __init__(self):
        # Initialize provider based on settings
        if settings.AI_PROVIDER == "ollama":
            self.provider = OllamaProvider(base_url=settings.OLLAMA_BASE_URL)
        else:
            self.provider = LocalHeuristicProvider()

    def run_full_detection(
        self, data: List[Dict[str, Any]], organization_id: str
    ) -> Dict[str, Any]:
        """
        Run anomaly detection on responses for a specific organization.
        """
        app_logger.info(
            f"AnomalyDetectionService: Running full detection for org {organization_id}"
        )
        try:
            if not data:
                app_logger.info(
                    "AnomalyDetectionService: No data provided for detection"
                )
                return {"anomalies_detected": 0, "anomalies": []}

            # Ensure we only process data for the correct organization
            scoped_data = [
                d for d in data if d.get("organization_id") == organization_id
            ]
            app_logger.info(
                f"AnomalyDetectionService: Scoped data to {len(scoped_data)} items for org {organization_id}"
            )

            anomalies = self.provider.detect_anomalies(scoped_data)

            result = {
                "anomalies_detected": len(anomalies),
                "anomalies": anomalies,
                "organization_id": organization_id,
            }
            app_logger.info(
                f"AnomalyDetectionService: Successfully completed detection. Found {len(anomalies)} anomalies."
            )
            return result
        except Exception as e:
            error_logger.error(
                f"AnomalyDetectionService: Full detection failed: {str(e)}",
                exc_info=True,
            )
            raise

    def detect_spam(self, text: str) -> Dict[str, Any]:
        """
        Heuristic spam detection.
        """
        app_logger.info("AnomalyDetectionService: Detecting spam in text")
        try:
            if not text:
                app_logger.debug(
                    "AnomalyDetectionService: Empty text provided for spam detection"
                )
                return {"is_spam": False, "spam_score": 0}

            spam_keywords = ["lottery", "prize", "winner", "click here", "urgent"]
            text_lower = text.lower()
            positives = [kw for kw in spam_keywords if kw in text_lower]

            is_spam = len(positives) > 0
            result = {
                "is_spam": is_spam,
                "spam_score": 1.0 if is_spam else 0.0,
                "indicators": positives,
            }
            app_logger.info(
                f"AnomalyDetectionService: Spam detection completed. is_spam: {is_spam}"
            )
            return result
        except Exception as e:
            error_logger.error(
                f"AnomalyDetectionService: Spam detection failed: {str(e)}",
                exc_info=True,
            )
            return {"is_spam": False, "spam_score": 0, "error": str(e)}

    def update_baseline(self, *args, **kwargs):
        app_logger.info("AnomalyDetectionService: Updating baseline")
        try:
            return {"status": "baseline_updated"}
        except Exception as e:
            error_logger.error(
                f"AnomalyDetectionService: Baseline update failed: {str(e)}",
                exc_info=True,
            )
            raise

    def get_threshold_history(self, *args, **kwargs):
        form_id = kwargs.get("form_id")
        limit = int(kwargs.get("limit", 50))
        app_logger.info(
            f"AnomalyDetectionService: Getting threshold history for form {form_id}"
        )
        if not form_id:
            return []
        return [
            {
                "threshold_id": str(item.id),
                "form_id": item.form_id,
                "organization_id": item.organization_id,
                "thresholds": item.thresholds,
                "baseline_stats": item.baseline_stats,
                "sensitivity": item.sensitivity,
                "response_count": item.response_count,
                "created_by": item.created_by,
                "reason": item.reason,
                "is_manual": item.is_manual,
                "created_at": item.created_at.isoformat()
                if item.created_at
                else None,
            }
            for item in AnomalyThreshold.objects(form_id=form_id).order_by("-created_at").limit(limit)
        ]

    def get_latest_threshold(self, *args, **kwargs):
        form_id = kwargs.get("form_id")
        sensitivity = kwargs.get("sensitivity")
        app_logger.info(
            f"AnomalyDetectionService: Getting latest threshold for form {form_id}"
        )
        if not form_id:
            return None
        query = AnomalyThreshold.objects(form_id=form_id)
        if sensitivity:
            query = query(sensitivity=sensitivity)
        item = query.order_by("-created_at").first()
        if not item:
            return None
        return {
            "threshold_id": str(item.id),
            "form_id": item.form_id,
            "organization_id": item.organization_id,
            "thresholds": item.thresholds,
            "baseline_stats": item.baseline_stats,
            "sensitivity": item.sensitivity,
            "response_count": item.response_count,
            "created_by": item.created_by,
            "reason": item.reason,
            "is_manual": item.is_manual,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }

    def set_manual_threshold(self, *args, **kwargs):
        form_id = kwargs.get("form_id")
        thresholds = kwargs.get("thresholds") or {}
        created_by = kwargs.get("created_by") or "system"
        reason = kwargs.get("reason")
        app_logger.info(
            f"AnomalyDetectionService: Setting manual threshold for form {form_id}"
        )
        if not form_id or not thresholds:
            raise ValueError("form_id and thresholds are required")

        form = Form.objects(id=form_id).first()
        organization_id = getattr(form, "organization_id", None) or ""
        record = AnomalyThreshold(
            form_id=str(form_id),
            organization_id=organization_id,
            thresholds=thresholds,
            baseline_stats=kwargs.get("baseline_stats") or {},
            sensitivity=kwargs.get("sensitivity") or "manual",
            response_count=int(kwargs.get("response_count", 0)),
            created_by=str(created_by),
            reason=reason,
            is_manual=True,
        )
        record.save()
        return {
            "threshold_id": str(record.id),
            "thresholds": record.thresholds,
            "baseline_stats": record.baseline_stats,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    def scan_batch(self, *args, **kwargs):
        app_logger.info("AnomalyDetectionService: Initiating batch scan")
        return {"status": "batch_scan_initiated"}


anomaly_detection_service = AnomalyDetectionService()
