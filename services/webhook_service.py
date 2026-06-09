import json
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from config.settings import settings
from models.WebhookDeliveryLog import WebhookDeliveryLog
from services.redis_service import redis_service
from logger.unified_logger import app_logger, error_logger, audit_logger


class WebhookService:
    """
    Webhook delivery service backed by MongoDB with Redis as a cache fallback.
    """

    HISTORY_KEY = "webhook:history"
    STATUS_KEY_PREFIX = "webhook:status:"
    LOG_KEY = "webhook:logs"
    DEFAULT_MAX_RETRIES = 3
    HISTORY_LIMIT = 1000

    @classmethod
    def list_webhooks(cls, form_id, user_id):
        app_logger.info(f"Listing webhooks for form {form_id} by user {user_id}")
        return []

    @classmethod
    def create_webhook(cls, **kwargs):
        app_logger.info("Creating new webhook stub")
        audit_logger.info(
            "Webhook created (stub)",
            extra={"event": "webhook_created", "webhook_id": "stub_webhook_id"},
        )
        return {"id": "stub_webhook_id"}

    @classmethod
    def get_webhook(cls, webhook_id, user_id):
        app_logger.info(f"Fetching webhook {webhook_id} for user {user_id}")
        return None

    @classmethod
    def construct_delivery_envelope(cls, payload, attempt=1):
        return {
            "payload": payload,
            "retry_count": attempt,
            "max_retries": cls.DEFAULT_MAX_RETRIES,
            "next_retry_backoff": (2**attempt) * 10,
            "status": "pending_delivery",
        }

    @classmethod
    def delete_webhook(cls, webhook_id, user_id):
        app_logger.info(f"Deleting webhook {webhook_id} by user {user_id}")
        audit_logger.info(
            f"Webhook {webhook_id} deleted by user {user_id}",
            extra={
                "event": "webhook_deleted",
                "webhook_id": webhook_id,
                "user_id": user_id,
            },
        )
        return True

    @classmethod
    def trigger_test(cls, webhook_id, user_id):
        app_logger.info(f"Triggering test for webhook {webhook_id} by user {user_id}")
        return {"success": True}

    @classmethod
    def get_logs(cls, webhook_id, user_id, limit=50):
        app_logger.info(f"Fetching logs for webhook {webhook_id} by user {user_id}")
        return cls.get_webhook_logs(limit=limit)

    @classmethod
    def send_webhook(
        cls,
        *,
        url: str,
        payload: Dict[str, Any],
        webhook_id: str,
        form_id: str,
        created_by: Optional[str] = None,
        max_retries: int = 3,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        schedule_for: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        app_logger.info(f"Preparing to send webhook {webhook_id} to {url}")
        delivery_id = (
            f"{webhook_id}:{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        )
        delivery_record = {
            "delivery_id": delivery_id,
            "webhook_id": webhook_id,
            "form_id": form_id,
            "url": url,
            "created_by": created_by,
            "organization_id": cls._extract_organization_id(payload),
            "max_retries": max_retries or cls.DEFAULT_MAX_RETRIES,
            "retry_count": 0,
            "status": "scheduled" if schedule_for else "pending",
            "scheduled_for": schedule_for.isoformat() if schedule_for else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_error": None,
        }
        cls._save_status(delivery_id, delivery_record)

        if schedule_for:
            app_logger.info(f"Webhook {delivery_id} scheduled for {schedule_for}")
            cls._append_history(delivery_record)
            return delivery_record

        return cls._deliver(
            delivery_id=delivery_id,
            webhook_id=webhook_id,
            form_id=form_id,
            url=url,
            payload=payload,
            headers=headers,
            timeout=timeout,
            max_retries=max_retries or cls.DEFAULT_MAX_RETRIES,
            created_by=created_by,
        )

    @classmethod
    def trigger_webhook(
        cls,
        webhook_id: Optional[str],
        data: Dict[str, Any],
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        app_logger.info(f"Triggering webhook {webhook_id}")
        if not webhook_id:
            error_logger.error("webhook_id is required for trigger_webhook")
            raise ValueError("webhook_id is required")

        payload = dict(data or {})
        if organization_id and "organization_id" not in payload:
            payload["organization_id"] = organization_id

        url = payload.get("url")
        form_id = payload.get("form_id", "unknown")
        if not url:
            error_logger.error("Webhook retry payload missing url")
            raise ValueError("Webhook retry payload missing url")

        headers = payload.get("headers")
        timeout = int(payload.get("timeout", 30))
        max_retries = int(payload.get("max_retries", cls.DEFAULT_MAX_RETRIES))
        body = payload.get("payload", payload)

        return cls.send_webhook(
            url=url,
            payload=body,
            webhook_id=webhook_id,
            form_id=form_id,
            created_by=payload.get("created_by"),
            max_retries=max_retries,
            headers=headers,
            timeout=timeout,
        )

    @classmethod
    def get_webhook_status(cls, delivery_id: str) -> Optional[Dict[str, Any]]:
        cached = redis_service.cache.get(f"{cls.STATUS_KEY_PREFIX}{delivery_id}")
        if cached:
            return cached

        log = WebhookDeliveryLog.objects(delivery_id=delivery_id).first()
        return log.to_dict() if log else None

    @classmethod
    def get_webhook_history(
        cls,
        form_id: Optional[str] = None,
        webhook_id: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Dict[str, Any]:
        app_logger.info(
            f"Fetching webhook history (form_id={form_id}, webhook_id={webhook_id}, status={status})"
        )
        query = WebhookDeliveryLog.objects
        if form_id:
            query = query(form_id=form_id)
        if webhook_id:
            query = query(webhook_id=webhook_id)
        if status:
            query = query(status=status)
        entries = [cls._serialize_delivery_log(log) for log in query.order_by("-created_at")]
        filtered = []
        for entry in entries:
            filtered.append(entry)

        start = max(page - 1, 0) * per_page
        end = start + per_page
        return {
            "items": filtered[start:end],
            "page": page,
            "per_page": per_page,
            "total": len(filtered),
        }

    @classmethod
    def retry_webhook(
        cls, delivery_id: str, reset_count: bool = False
    ) -> Dict[str, Any]:
        app_logger.info(
            f"Retrying webhook delivery {delivery_id} (reset_count={reset_count})"
        )
        record = cls.get_webhook_status(delivery_id)
        if not record:
            error_logger.error(f"Webhook delivery {delivery_id} not found for retry")
            raise ValueError("Webhook delivery not found")

        payload = {
            "url": record.get("url"),
            "form_id": record.get("form_id"),
            "headers": record.get("headers"),
            "timeout": record.get("timeout", 30),
            "max_retries": record.get("max_retries", cls.DEFAULT_MAX_RETRIES),
            "created_by": record.get("created_by"),
            "organization_id": record.get("organization_id"),
            "payload": record.get("payload", {}),
        }

        if reset_count:
            payload["max_retries"] = cls.DEFAULT_MAX_RETRIES

        return cls.trigger_webhook(
            record.get("webhook_id"),
            payload,
            organization_id=record.get("organization_id"),
        )

    @classmethod
    def cancel_webhook(cls, delivery_id: str) -> Dict[str, Any]:
        app_logger.info(f"Cancelling webhook delivery {delivery_id}")
        record = cls.get_webhook_status(delivery_id)
        if not record:
            error_logger.error(
                f"Webhook delivery {delivery_id} not found for cancellation"
            )
            raise ValueError("Webhook delivery not found")

        record["status"] = "cancelled"
        record["cancelled_at"] = datetime.now(timezone.utc).isoformat()
        cls._save_status(delivery_id, record)
        cls._append_history(record)
        audit_logger.info(
            f"Webhook delivery {delivery_id} cancelled",
            extra={"event": "webhook_delivery_cancelled", "delivery_id": delivery_id},
        )
        return record

    @classmethod
    def get_webhook_logs(
        cls,
        url: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        app_logger.info(f"Fetching webhook logs (url={url}, status={status})")
        query = WebhookDeliveryLog.objects
        if url:
            query = query(url=url)
        if status:
            query = query(status=status)
        return [cls._serialize_delivery_log(log) for log in query.order_by("-created_at")[:limit]]

    @classmethod
    def safe_transform_payload(cls, template_str: str, event_data: dict) -> str:
        import string

        try:
            flat_data = {
                k: str(v)
                for k, v in event_data.items()
                if not isinstance(v, (dict, list))
            }
            template = string.Template(template_str)
            return template.safe_substitute(**flat_data)
        except Exception as exc:
            app_logger.warning(
                f"Webhook Transform failure. Proceeding with raw JSON. {exc}"
            )
            return json.dumps(event_data)

    @classmethod
    def _canonical_payload(cls, payload: Dict[str, Any]) -> bytes:
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")

    @classmethod
    def _build_signed_headers(
        cls, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        signed_headers = dict(headers or {})
        secret = None
        if headers:
            secret = (
                headers.get("X-Webhook-Secret")
                or headers.get("Webhook-Secret")
                or headers.get("X-Webhook-Signature-Secret")
            )
        if not secret:
            secret = settings.JWT_SECRET_KEY
        digest = hmac.new(
            secret.encode("utf-8"),
            cls._canonical_payload(payload),
            hashlib.sha256,
        ).hexdigest()
        signature_value = f"sha256={digest}"
        signed_headers["X-FBP-Signature"] = signature_value
        signed_headers["X-RIDP-Signature"] = signature_value
        return signed_headers

    @classmethod
    def _deliver(
        cls,
        *,
        delivery_id: str,
        webhook_id: str,
        form_id: str,
        url: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]],
        timeout: int,
        max_retries: int,
        created_by: Optional[str],
    ) -> Dict[str, Any]:
        app_logger.info(f"Delivering webhook {delivery_id} to {url}")
        signed_headers = cls._build_signed_headers(payload, headers=headers)
        record = {
            "delivery_id": delivery_id,
            "webhook_id": webhook_id,
            "form_id": form_id,
            "url": url,
            "payload": payload,
            "headers": signed_headers,
            "timeout": timeout,
            "max_retries": max_retries,
            "created_by": created_by,
            "organization_id": cls._extract_organization_id(payload),
            "retry_count": 0,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_error": None,
        }

        try:
            response = requests.post(
                url, json=payload, headers=signed_headers, timeout=timeout
            )
            response.raise_for_status()
            record["status"] = "delivered"
            record["response_status"] = response.status_code
            record["delivered_at"] = datetime.now(timezone.utc).isoformat()
            app_logger.info(
                f"Webhook {delivery_id} delivered successfully with status {response.status_code}"
            )
        except requests.RequestException as exc:
            record["status"] = "failed"
            record["retry_count"] = 1
            record["last_error"] = str(exc)
            error_logger.error(f"Webhook delivery failed for {delivery_id}: {exc}")
        cls._save_status(delivery_id, record)
        cls._append_history(record)
        cls._append_log(record)
        return record

    @classmethod
    def _extract_organization_id(cls, payload: Dict[str, Any]) -> Optional[str]:
        if not isinstance(payload, dict):
            return None
        org_id = payload.get("organization_id")
        if org_id is None and isinstance(payload.get("data"), dict):
            org_id = payload["data"].get("organization_id")
        return str(org_id) if org_id else None

    @classmethod
    def _save_status(cls, delivery_id: str, record: Dict[str, Any]) -> None:
        cls._upsert_delivery_log(record)
        redis_service.cache.set(
            f"{cls.STATUS_KEY_PREFIX}{delivery_id}", record, ttl=7 * 24 * 3600
        )

    @classmethod
    def _load_history(cls) -> List[Dict[str, Any]]:
        return [cls._serialize_delivery_log(log) for log in WebhookDeliveryLog.objects.order_by("-created_at")]

    @classmethod
    def _append_history(cls, record: Dict[str, Any]) -> None:
        cls._upsert_delivery_log(record)
        history = cls._load_history()
        redis_service.cache.set(cls.HISTORY_KEY, history[: cls.HISTORY_LIMIT], ttl=7 * 24 * 3600)

    @classmethod
    def _append_log(cls, record: Dict[str, Any]) -> None:
        log_record = dict(record)
        log_record["log_context"] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "organization_id": record.get("organization_id"),
            "last_error": record.get("last_error"),
        }
        cls._upsert_delivery_log(log_record)
        logs = redis_service.cache.get(cls.LOG_KEY) or []
        logs.insert(
            0,
            {
                "delivery_id": record.get("delivery_id"),
                "url": record.get("url"),
                "status": record.get("status"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "organization_id": record.get("organization_id"),
                "last_error": record.get("last_error"),
            },
        )
        redis_service.cache.set(cls.LOG_KEY, logs[: cls.HISTORY_LIMIT], ttl=7 * 24 * 3600)

    @classmethod
    def _serialize_delivery_log(cls, log: WebhookDeliveryLog) -> Dict[str, Any]:
        data = log.to_dict()
        if "id" in data and isinstance(data["id"], str):
            data["id"] = data["id"]
        return data

    @classmethod
    def _upsert_delivery_log(cls, record: Dict[str, Any]) -> WebhookDeliveryLog:
        delivery_id = record.get("delivery_id")
        if not delivery_id:
            raise ValueError("delivery_id is required")

        existing = WebhookDeliveryLog.objects(delivery_id=delivery_id).first()
        if existing:
            for field in (
                "webhook_id",
                "form_id",
                "url",
                "created_by",
                "organization_id",
                "payload",
                "headers",
                "timeout",
                "max_retries",
                "retry_count",
                "status",
                "scheduled_for",
                "last_error",
                "response_status",
                "delivered_at",
                "cancelled_at",
            ):
                if field in record and record.get(field) is not None:
                    value = record.get(field)
                    if field in {"scheduled_for", "delivered_at", "cancelled_at"}:
                        value = WebhookDeliveryLog._coerce_datetime(value)
                    setattr(existing, field, value)
            existing.log_context = record.get("log_context", existing.log_context or {})
            existing.save()
            return existing

        log = WebhookDeliveryLog.from_record(record)
        log.save()
        return log


webhook_service = WebhookService()
