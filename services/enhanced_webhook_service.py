"""
services/enhanced_webhook_service.py
Enhanced webhook service with HMAC signing, delivery logs, and retry logic.
"""

import json
import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import requests

from config.settings import settings
from models.integration import WebhookDelivery as WebhookDeliveryLog
from models.form import Form
from models.components import Trigger
from services.redis_service import redis_service
from logger.unified_logger import app_logger, error_logger, audit_logger
from utils.exceptions import ValidationError, NotFoundError


class EnhancedWebhookService:
    """
    Enhanced webhook delivery service with HMAC signing, delivery logs, and retry logic.
    """

    HISTORY_KEY = "webhook:history"
    STATUS_KEY_PREFIX = "webhook:status:"
    LOG_KEY = "webhook:logs"
    DEFAULT_MAX_RETRIES = 3
    HISTORY_LIMIT = 1000
    SIGNATURE_ALGORITHM = "sha256"
    SIGNATURE_HEADER = "X-FBP-Signature"
    TIMESTAMP_HEADER = "X-FBP-Timestamp"
    NONCE_HEADER = "X-FBP-Nonce"
    RETRY_DELAYS = [60, 300, 900]  # 1min, 5min, 15min

    @classmethod
    def list_webhooks(cls, form_id, user_id):
        """List webhooks for a form."""
        app_logger.info(f"Listing webhooks for form {form_id} by user {user_id}")
        form = Form.objects(id=form_id, is_deleted=False).first()
        if not form:
            return []
        if user_id and not cls._can_manage_form(form, str(user_id)):
            app_logger.warning(
                f"User {user_id} not authorized to list webhooks for form {form_id}"
            )
            return []

        webhooks = [
            cls._serialize_trigger(form, trigger)
            for trigger in (form.triggers or [])
            if getattr(trigger, "action_type", None) == "webhook"
        ]
        webhooks.sort(key=lambda item: (item.get("order") or "", item.get("name") or ""))
        return webhooks

    @classmethod
    def create_webhook(cls, **kwargs):
        """Create a new webhook."""
        app_logger.info("Creating new webhook")
        form_id = kwargs.get("form_id")
        if not form_id:
            raise ValidationError("form_id is required")

        form = Form.objects(id=form_id, is_deleted=False).first()
        if not form:
            raise ValidationError("Form not found")

        user_id = kwargs.get("user_id") or kwargs.get("created_by")
        if user_id and not cls._can_manage_form(form, str(user_id)):
            raise PermissionError("User is not authorized to manage webhooks for this form")

        webhook_id = str(kwargs.get("webhook_id") or kwargs.get("id") or uuid4())
        existing = cls.get_webhook(webhook_id, user_id)
        if existing:
            raise ValidationError("Webhook already exists")

        # Validate webhook URL
        url = kwargs.get("action_config", {}).get("url") or kwargs.get("config", {}).get("url")
        if not url:
            raise ValidationError("Webhook URL is required")

        # Validate webhook secret for HMAC signing
        secret = kwargs.get("action_config", {}).get("secret") or kwargs.get("config", {}).get("secret")
        if secret and len(secret) < 16:
            raise ValidationError("Webhook secret must be at least 16 characters long")

        trigger = Trigger(
            name=kwargs.get("name") or webhook_id,
            event_type=kwargs.get("event_type") or kwargs.get("event") or "on_submit",
            action_type="webhook",
            action_config=dict(kwargs.get("action_config") or kwargs.get("config") or {}),
            custom_script=kwargs.get("custom_script"),
            is_active=kwargs.get("is_active", True),
            order=str(kwargs.get("order") or (len(form.triggers or []) + 1)),
            meta_data=dict(kwargs.get("meta_data") or {}),
        )
        trigger.meta_data["webhook_id"] = webhook_id
        trigger.meta_data["created_at"] = datetime.now(timezone.utc).isoformat()
        trigger.meta_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        if kwargs.get("description"):
            trigger.meta_data["description"] = kwargs["description"]

        form.triggers = list(form.triggers or [])
        form.triggers.append(trigger)
        form.save()

        created = cls._serialize_trigger(form, trigger)
        audit_logger.info(
            "Webhook created",
            extra={
                "event": "webhook_created",
                "webhook_id": webhook_id,
                "form_id": form_id,
                "created_by": str(user_id or ""),
            },
        )
        return created

    @classmethod
    def get_webhook(cls, webhook_id, user_id):
        """Get a webhook by ID."""
        app_logger.info(f"Fetching webhook {webhook_id} for user {user_id}")
        match = cls._find_webhook(webhook_id)
        if not match:
            return None
        form, trigger = match
        if user_id and not cls._can_manage_form(form, str(user_id)):
            return None
        return cls._serialize_trigger(form, trigger)

    @classmethod
    def update_webhook(cls, webhook_id, user_id, **kwargs):
        """Update a webhook."""
        app_logger.info(f"Updating webhook {webhook_id} by user {user_id}")
        match = cls._find_webhook(webhook_id)
        if not match:
            raise NotFoundError(f"Webhook not found: {webhook_id}")
        form, trigger = match
        if user_id and not cls._can_manage_form(form, str(user_id)):
            raise PermissionError("User is not authorized to update this webhook")

        # Update trigger fields
        if "name" in kwargs:
            trigger.name = kwargs["name"]
        if "event_type" in kwargs:
            trigger.event_type = kwargs["event_type"]
        if "action_config" in kwargs:
            trigger.action_config = dict(kwargs["action_config"])
        if "is_active" in kwargs:
            trigger.is_active = kwargs["is_active"]
        if "order" in kwargs:
            trigger.order = str(kwargs["order"])

        trigger.meta_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        if "description" in kwargs:
            trigger.meta_data["description"] = kwargs["description"]

        form.save()

        audit_logger.info(
            "Webhook updated",
            extra={
                "event": "webhook_updated",
                "webhook_id": webhook_id,
                "form_id": str(form.id),
                "updated_by": str(user_id),
            },
        )
        return cls._serialize_trigger(form, trigger)

    @classmethod
    def delete_webhook(cls, webhook_id, user_id):
        """Delete a webhook."""
        app_logger.info(f"Deleting webhook {webhook_id} by user {user_id}")
        match = cls._find_webhook(webhook_id)
        if not match:
            return False
        form, trigger = match
        if user_id and not cls._can_manage_form(form, str(user_id)):
            raise PermissionError(
                "User is not authorized to delete webhooks for this form"
            )

        form.triggers = [
            existing
            for existing in (form.triggers or [])
            if cls._trigger_id(existing) != webhook_id
        ]
        form.save()
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
        """Trigger a test webhook delivery."""
        app_logger.info(f"Triggering test for webhook {webhook_id} by user {user_id}")
        match = cls._find_webhook(webhook_id)
        if not match:
            raise ValidationError("Webhook not found")
        form, trigger = match
        if user_id and not cls._can_manage_form(form, str(user_id)):
            raise PermissionError("User is not authorized to test this webhook")

        action_config = trigger.action_config or {}
        url = action_config.get("url")
        if not url:
            raise ValidationError("Webhook URL is required")

        payload = {
            "event": "webhook.test",
            "webhook_id": webhook_id,
            "form_id": str(form.id),
            "created_by": str(user_id or ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trigger_name": trigger.name,
        }
        return cls.send_webhook(
            url=url,
            payload=payload,
            webhook_id=webhook_id,
            form_id=str(form.id),
            created_by=str(user_id) if user_id else None,
            max_retries=int(action_config.get("max_retries", cls.DEFAULT_MAX_RETRIES)),
            headers=action_config.get("headers"),
            secret=action_config.get("secret"),
            timeout=int(action_config.get("timeout", 30)),
        )

    @classmethod
    def get_logs(cls, webhook_id, user_id, limit=50):
        """Get webhook delivery logs."""
        app_logger.info(f"Fetching logs for webhook {webhook_id} by user {user_id}")
        if webhook_id:
            return cls.get_webhook_logs(webhook_id=webhook_id, limit=limit)
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
        secret: Optional[str] = None,
        timeout: int = 30,
        schedule_for: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Send a webhook with HMAC signing."""
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
            secret=secret,
            created_by=created_by,
        )

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
        secret: Optional[str],
        created_by: Optional[str],
    ) -> Dict[str, Any]:
        """Deliver webhook with HMAC signing and retry logic."""
        app_logger.info(f"Delivering webhook {delivery_id} to {url}")
        
        # Prepare signed headers
        signed_headers = cls._build_signed_headers(payload, secret, headers)
        
        # Add timestamp and nonce for replay protection
        timestamp = str(int(time.time()))
        nonce = str(uuid4())
        signed_headers[cls.TIMESTAMP_HEADER] = timestamp
        signed_headers[cls.NONCE_HEADER] = nonce

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
                url, 
                json=payload, 
                headers=signed_headers, 
                timeout=timeout
            )
            response.raise_for_status()
            
            record["status"] = "delivered"
            record["response_status"] = response.status_code
            record["delivered_at"] = datetime.now(timezone.utc).isoformat()
            record["response_body"] = response.text[:1000]  # Store first 1000 chars
            
            app_logger.info(
                f"Webhook {delivery_id} delivered successfully with status {response.status_code}"
            )
        except requests.RequestException as exc:
            record["status"] = "failed"
            record["retry_count"] = 1
            record["last_error"] = str(exc)
            error_logger.error(f"Webhook delivery failed for {delivery_id}: {exc}")
            
            # Schedule retry if not max retries
            if record["retry_count"] < max_retries:
                record["status"] = "retrying"
                record["next_retry_at"] = (
                    datetime.now(timezone.utc) + 
                    timedelta(seconds=cls.RETRY_DELAYS[record["retry_count"] - 1])
                ).isoformat()
                # Schedule retry task
                from tasks.webhook_tasks import retry_webhook_delivery
                retry_webhook_delivery.apply_async(
                    args=[delivery_id],
                    countdown=cls.RETRY_DELAYS[record["retry_count"] - 1]
                )

        cls._save_status(delivery_id, record)
        cls._append_history(record)
        cls._append_log(record)
        return record

    @classmethod
    def _build_signed_headers(
        cls, payload: Dict[str, Any], secret: Optional[str] = None, 
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Build headers with HMAC signature."""
        signed_headers = dict(headers or {})
        
        # Use webhook secret or fall back to JWT secret
        signing_secret = secret or settings.JWT_SECRET_KEY
        
        # Create canonical payload for signing
        canonical_payload = cls._canonical_payload(payload)
        
        # Generate HMAC signature
        digest = hmac.new(
            signing_secret.encode("utf-8"),
            canonical_payload,
            getattr(hashlib, cls.SIGNATURE_ALGORITHM)
        ).hexdigest()
        
        signature_value = f"{cls.SIGNATURE_ALGORITHM}={digest}"
        signed_headers[cls.SIGNATURE_HEADER] = signature_value
        
        return signed_headers

    @classmethod
    def _canonical_payload(cls, payload: Dict[str, Any]) -> bytes:
        """Create canonical payload for signing."""
        return json.dumps(
            payload, 
            sort_keys=True, 
            separators=(",", ":"), 
            ensure_ascii=False
        ).encode("utf-8")

    @classmethod
    def verify_webhook_signature(cls, payload: bytes, signature: str, secret: str) -> bool:
        """Verify webhook signature."""
        try:
            expected_signature = hmac.new(
                secret.encode("utf-8"),
                payload,
                getattr(hashlib, cls.SIGNATURE_ALGORITHM)
            ).hexdigest()
            
            # Compare signatures securely
            signature_parts = signature.split("=", 1)
            if len(signature_parts) != 2:
                return False
            
            algorithm, received_signature = signature_parts
            if algorithm != cls.SIGNATURE_ALGORITHM:
                return False
            
            return hmac.compare_digest(received_signature, expected_signature)
        except Exception:
            return False

    @classmethod
    def retry_webhook_delivery(cls, delivery_id: str) -> Dict[str, Any]:
        """Retry a failed webhook delivery."""
        app_logger.info(f"Retrying webhook delivery {delivery_id}")
        record = cls.get_webhook_status(delivery_id)
        if not record:
            raise ValidationError("Webhook delivery not found")

        if record["status"] not in ["failed", "retrying"]:
            raise ValidationError("Webhook delivery is not in a retryable state")

        if record["retry_count"] >= record["max_retries"]:
            raise ValidationError("Maximum retry attempts exceeded")

        # Update retry count
        record["retry_count"] += 1
        record["status"] = "retrying"
        record["next_retry_at"] = (
            datetime.now(timezone.utc) + 
            timedelta(seconds=cls.RETRY_DELAYS[record["retry_count"] - 1])
        ).isoformat()

        # Prepare for redelivery
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

        return cls.trigger_webhook(
            record.get("webhook_id"),
            payload,
            organization_id=record.get("organization_id"),
        )

    @classmethod
    def get_webhook_status(cls, delivery_id: str) -> Optional[Dict[str, Any]]:
        """Get webhook delivery status."""
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
        """Get webhook delivery history."""
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
    def get_webhook_logs(
        cls,
        webhook_id: Optional[str] = None,
        url: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get webhook delivery logs."""
        app_logger.info(
            f"Fetching webhook logs (webhook_id={webhook_id}, url={url}, status={status})"
        )
        query = WebhookDeliveryLog.objects
        if webhook_id:
            query = query(webhook_id=webhook_id)
        if url:
            query = query(url=url)
        if status:
            query = query(status=status)
        return [cls._serialize_delivery_log(log) for log in query.order_by("-created_at")[:limit]]

    @classmethod
    def _save_status(cls, delivery_id: str, record: Dict[str, Any]) -> None:
        """Save webhook delivery status."""
        cls._upsert_delivery_log(record)
        redis_service.cache.set(
            f"{cls.STATUS_KEY_PREFIX}{delivery_id}", record, ttl=7 * 24 * 3600
        )

    @classmethod
    def _append_history(cls, record: Dict[str, Any]) -> None:
        """Append to webhook delivery history."""
        cls._upsert_delivery_log(record)
        history = cls._load_history()
        redis_service.cache.set(cls.HISTORY_KEY, history[: cls.HISTORY_LIMIT], ttl=7 * 24 * 3600)

    @classmethod
    def _append_log(cls, record: Dict[str, Any]) -> None:
        """Append to webhook delivery log."""
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
    def _upsert_delivery_log(cls, record: Dict[str, Any]) -> WebhookDeliveryLog:
        """Upsert webhook delivery log."""
        delivery_id = record.get("delivery_id")
        if not delivery_id:
            raise ValidationError("delivery_id is required")

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
                "response_body",
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

    @classmethod
    def _load_history(cls) -> List[Dict[str, Any]]:
        """Load webhook delivery history."""
        return [cls._serialize_delivery_log(log) for log in WebhookDeliveryLog.objects.order_by("-created_at")]

    @classmethod
    def _serialize_delivery_log(cls, log: WebhookDeliveryLog) -> Dict[str, Any]:
        """Serialize webhook delivery log."""
        data = log.to_dict()
        if "id" in data and isinstance(data["id"], str):
            data["id"] = data["id"]
        return data

    @classmethod
    def _trigger_id(cls, trigger: Trigger) -> str:
        """Get trigger ID."""
        meta_data = getattr(trigger, "meta_data", {}) or {}
        return str(meta_data.get("webhook_id") or meta_data.get("id") or "")

    @classmethod
    def _serialize_trigger(cls, form: Form, trigger: Trigger) -> Dict[str, Any]:
        """Serialize trigger."""
        meta_data = dict(getattr(trigger, "meta_data", {}) or {})
        webhook_id = cls._trigger_id(trigger) or meta_data.get("webhook_id") or ""
        return {
            "id": webhook_id,
            "webhook_id": webhook_id,
            "form_id": str(form.id),
            "name": trigger.name,
            "event_type": trigger.event_type,
            "action_type": trigger.action_type,
            "action_config": dict(trigger.action_config or {}),
            "custom_script": trigger.custom_script,
            "is_active": bool(trigger.is_active),
            "order": trigger.order,
            "meta_data": meta_data,
        }

    @classmethod
    def _find_webhook(cls, webhook_id: str):
        """Find webhook by ID."""
        if not webhook_id:
            return None
        for form in Form.objects(is_deleted=False):
            for trigger in (form.triggers or []):
                if getattr(trigger, "action_type", None) != "webhook":
                    continue
                if cls._trigger_id(trigger) == str(webhook_id):
                    return form, trigger
        return None

    @classmethod
    def _can_manage_form(cls, form: Form, user_id: str) -> bool:
        """Check if user can manage form."""
        if not user_id:
            return False
        if str(getattr(form, "created_by", "")) == str(user_id):
            return True
        editors = [str(editor) for editor in (form.editors or [])]
        return str(user_id) in editors

    @classmethod
    def _extract_organization_id(cls, payload: Dict[str, Any]) -> Optional[str]:
        """Extract organization ID from payload."""
        if not isinstance(payload, dict):
            return None
        org_id = payload.get("organization_id")
        if org_id is None and isinstance(payload.get("data"), dict):
            org_id = payload["data"].get("organization_id")
        return str(org_id) if org_id else None


enhanced_webhook_service = EnhancedWebhookService()