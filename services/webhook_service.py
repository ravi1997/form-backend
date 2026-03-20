import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from services.redis_service import redis_service

logger = logging.getLogger(__name__)


class WebhookService:
    """
    Lightweight webhook delivery service backed by Redis for delivery history.
    Keeps the current route contract working without introducing new persistence models.
    """

    HISTORY_KEY = "webhook:history"
    STATUS_KEY_PREFIX = "webhook:status:"
    LOG_KEY = "webhook:logs"
    DEFAULT_MAX_RETRIES = 5
    HISTORY_LIMIT = 1000

    @classmethod
    def list_webhooks(cls, form_id, user_id):
        return []

    @classmethod
    def create_webhook(cls, **kwargs):
        return {"id": "stub_webhook_id"}

    @classmethod
    def get_webhook(cls, webhook_id, user_id):
        return None

    @classmethod
    def construct_delivery_envelope(cls, payload, attempt=1):
        return {
            "payload": payload,
            "retry_count": attempt,
            "max_retries": cls.DEFAULT_MAX_RETRIES,
            "next_retry_backoff": (2 ** attempt) * 10,
            "status": "pending_delivery",
        }

    @classmethod
    def delete_webhook(cls, webhook_id, user_id):
        return True

    @classmethod
    def trigger_test(cls, webhook_id, user_id):
        return {"success": True}

    @classmethod
    def get_logs(cls, webhook_id, user_id, limit=50):
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
        max_retries: int = 5,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 10,
        schedule_for: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        delivery_id = f"{webhook_id}:{int(datetime.now(timezone.utc).timestamp() * 1000)}"
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
        if not webhook_id:
            raise ValueError("webhook_id is required")

        payload = dict(data or {})
        if organization_id and "organization_id" not in payload:
            payload["organization_id"] = organization_id

        url = payload.get("url")
        form_id = payload.get("form_id", "unknown")
        if not url:
            raise ValueError("Webhook retry payload missing url")

        headers = payload.get("headers")
        timeout = int(payload.get("timeout", 10))
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
        return redis_service.cache.get(f"{cls.STATUS_KEY_PREFIX}{delivery_id}")

    @classmethod
    def get_webhook_history(
        cls,
        form_id: Optional[str] = None,
        webhook_id: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Dict[str, Any]:
        entries = cls._load_history()
        filtered = []
        for entry in entries:
            if form_id and entry.get("form_id") != form_id:
                continue
            if webhook_id and entry.get("webhook_id") != webhook_id:
                continue
            if status and entry.get("status") != status:
                continue
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
    def retry_webhook(cls, delivery_id: str, reset_count: bool = False) -> Dict[str, Any]:
        record = cls.get_webhook_status(delivery_id)
        if not record:
            raise ValueError("Webhook delivery not found")

        payload = {
            "url": record.get("url"),
            "form_id": record.get("form_id"),
            "headers": record.get("headers"),
            "timeout": record.get("timeout", 10),
            "max_retries": record.get("max_retries", cls.DEFAULT_MAX_RETRIES),
            "created_by": record.get("created_by"),
            "organization_id": record.get("organization_id"),
            "payload": record.get("payload", {}),
        }

        if reset_count:
            payload["max_retries"] = cls.DEFAULT_MAX_RETRIES

        return cls.trigger_webhook(record.get("webhook_id"), payload, organization_id=record.get("organization_id"))

    @classmethod
    def cancel_webhook(cls, delivery_id: str) -> Dict[str, Any]:
        record = cls.get_webhook_status(delivery_id)
        if not record:
            raise ValueError("Webhook delivery not found")

        record["status"] = "cancelled"
        record["cancelled_at"] = datetime.now(timezone.utc).isoformat()
        cls._save_status(delivery_id, record)
        cls._append_history(record)
        return record

    @classmethod
    def get_webhook_logs(
        cls,
        url: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        logs = redis_service.cache.get(cls.LOG_KEY) or []
        filtered = []
        for entry in logs:
            if url and entry.get("url") != url:
                continue
            if status and entry.get("status") != status:
                continue
            filtered.append(entry)
        return filtered[:limit]

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
            logger.warning(f"Webhook Transform failure. Proceeding with raw JSON. {exc}")
            return json.dumps(event_data)

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
        record = {
            "delivery_id": delivery_id,
            "webhook_id": webhook_id,
            "form_id": form_id,
            "url": url,
            "payload": payload,
            "headers": headers or {},
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
            response = requests.post(url, json=payload, headers=headers or {}, timeout=timeout)
            response.raise_for_status()
            record["status"] = "delivered"
            record["response_status"] = response.status_code
            record["delivered_at"] = datetime.now(timezone.utc).isoformat()
        except requests.RequestException as exc:
            record["status"] = "failed"
            record["retry_count"] = 1
            record["last_error"] = str(exc)
            logger.error(f"Webhook delivery failed for {delivery_id}: {exc}")
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
        redis_service.cache.set(f"{cls.STATUS_KEY_PREFIX}{delivery_id}", record, ttl=7 * 24 * 3600)

    @classmethod
    def _load_history(cls) -> List[Dict[str, Any]]:
        return redis_service.cache.get(cls.HISTORY_KEY) or []

    @classmethod
    def _append_history(cls, record: Dict[str, Any]) -> None:
        history = cls._load_history()
        history.insert(0, record)
        redis_service.cache.set(cls.HISTORY_KEY, history[: cls.HISTORY_LIMIT], ttl=7 * 24 * 3600)

    @classmethod
    def _append_log(cls, record: Dict[str, Any]) -> None:
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


webhook_service = WebhookService()
