import json
import logging
import time
import uuid
import socket
from datetime import datetime
from typing import Any, Callable, Dict
from services.redis_service import redis_service
from flask import has_request_context
from flask_jwt_extended import current_user
import opentelemetry.trace as trace

logger = logging.getLogger(__name__)

class EventBus:
    """
    Core Event Bus powered by Redis Streams.
    Provides durable, at-least-once delivery semantics via Consumer Groups,
    decoupling domain actions from robust background workers.
    """

    def publish(self, topic: str, payload: Dict[str, Any]):
        """Publish an event securely to a Redis stream."""
        try:
            envelope = {
                "event_id": str(uuid.uuid4()),
                "timestamp": str(time.time()),
                "payload": json.dumps(payload, default=self._json_default),
                "trace_id": format(trace.get_current_span().get_span_context().trace_id, '032x') if trace.get_current_span().is_recording() else None,
                "span_id": format(trace.get_current_span().get_span_context().span_id, '016x') if trace.get_current_span().is_recording() else None
            }
            if payload.get("organization_id"):
                envelope["organization_id"] = str(payload.get("organization_id"))
            elif has_request_context():
                try:
                    if current_user:
                        envelope["organization_id"] = getattr(current_user, "organization_id", "unknown")
                except Exception:
                    pass
            
            # XADD stores the payload in the stream map with max length limiting
            redis_service.cache.client.xadd(topic, envelope, maxlen=100000)
            logger.info(f"Streamed event to {topic}: {payload.get('id', 'unknown')}")
        except Exception as e:
            logger.error(f"Failed to publish stream event {topic}: {e}")

    @staticmethod
    def _message_get(message_data: dict, key: str, default: Any = None) -> Any:
        if key in message_data:
            return message_data.get(key, default)
        b_key = key.encode("utf-8")
        if b_key in message_data:
            return message_data.get(b_key, default)
        return default

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    def publish_to_dlq(self, topic: str, payload: Dict[str, Any], error_message: str):
        """Publish failed events to a dead letter queue."""
        dlq_topic = f"{topic}:dlq"
        try:
            payload["dlq_error"] = error_message
            self.publish(dlq_topic, payload)
        except Exception as e:
            logger.error(f"Failed to publish to DLQ {dlq_topic}: {e}")

    def subscribe(self, topic: str, handler: Callable[[Dict[str, Any]], None], group_name="default_workers", max_retries=3):
        """
        Subscribe to a topic. Uses Redis Consumer Groups ensuring messages are handled safely.
        This is a blocking polling loop if run in the main thread!
        """
        consumer_id = socket.gethostname()
        
        # Ensure base stream and group exist, mask BUSYGROUP errors if already created
        try:
            redis_service.cache.client.xgroup_create(topic, group_name, id='0-0', mkstream=True)
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                logger.error(f"Error creating consumer group {group_name} on {topic}: {e}")
                
        logger.info(f"Started durable stream listener loop for {topic} (Group: {group_name})")
        
        while True:
            try:
                # XREADGROUP pulls messages not yet ACKenowledged by this group, blocking up to 2s
                events = redis_service.cache.client.xreadgroup(group_name, consumer_id, {topic: '>'}, count=10, block=2000)
                if not events:
                    # Periodically check for pending messages (un-acked)
                    self._process_pending_messages(topic, group_name, consumer_id, handler, max_retries)
                    continue
                    
                for stream, messages in events:
                    for message_id, message_data in messages:
                        self._handle_message(topic, group_name, message_id, message_data, handler)
                            
            except Exception as e:
                logger.error(f"Stream polling error: {e}", exc_info=True)
                time.sleep(2)  # Backoff on connection drop

    def _handle_message(self, topic: str, group_name: str, message_id: str, message_data: dict, handler: Callable):
        payload_raw = self._message_get(message_data, "payload", "{}")
        if isinstance(payload_raw, bytes):
            payload_raw = payload_raw.decode("utf-8")
        data = json.loads(payload_raw or "{}")
        try:
            handler(data)
            redis_service.cache.client.xack(topic, group_name, message_id)
        except Exception as handler_error:
            logger.error(f"Stream handler error on {topic}: {handler_error}", exc_info=True)

    def _process_pending_messages(self, topic: str, group_name: str, consumer_id: str, handler: Callable, max_retries: int):
        try:
            # Check PEL (Pending Entries List)
            pending = redis_service.cache.client.xpending(topic, group_name)
            pending_count = pending.get("pending", 0) if isinstance(pending, dict) else 0
            if not pending or pending_count == 0:
                return

            # Claim long-pending messages (idle > 60s)
            min_idle_time = 60000 
            messages = redis_service.cache.client.xautoclaim(topic, group_name, consumer_id, min_idle_time, start_id='0-0', count=10)
            
            if messages and len(messages) > 1 and messages[1]:
                for message_id, message_data in messages[1]:
                    # Check delivery count to prevent infinite retries
                    # Since xautoclaim doesn't directly give us retry count like xpending does, we do a quick PEL check for this item
                    pel_item = redis_service.cache.client.xpending_range(topic, group_name, message_id, message_id, 1)
                    if pel_item:
                        delivery_count = pel_item[0].get("times_delivered") or pel_item[0].get("deliv", 0)
                        if delivery_count > max_retries:
                            logger.warning(f"Message {message_id} exceeded max retries. Moving to DLQ.")
                            payload_raw = self._message_get(message_data, "payload", "{}")
                            if isinstance(payload_raw, bytes):
                                payload_raw = payload_raw.decode("utf-8")
                            self.publish_to_dlq(topic, json.loads(payload_raw or "{}"), "Max retries exceeded")
                            redis_service.cache.client.xack(topic, group_name, message_id)
                            continue

                    self._handle_message(topic, group_name, message_id, message_data, handler)
        except Exception as e:
            logger.error(f"Error processing pending messages on {topic}: {e}", exc_info=True)

    def get_metrics(self) -> Dict[str, Any]:
        """Fetch basic metrics about streams and consumer lag."""
        metrics = {}
        # We can scan known topics or simply use a generic pattern.
        # Since we use redis_client, let's grab a few known topics for now.
        topics = ["form.submitted", "tenant.key.rotated"]
        for t in topics:
            try:
                length = redis_service.cache.client.xlen(t)
                dlq_length = redis_service.cache.client.xlen(f"{t}:dlq")
                
                # Check groups
                groups = redis_service.cache.client.xinfo_groups(t)
                group_metrics = []
                for g in groups:
                    group_metrics.append({
                        "name": g["name"],
                        "consumers": g["consumers"],
                        "pending": g["pending"],
                        "lag": g.get("lag", 0)
                    })
                
                metrics[t] = {
                    "length": length,
                    "dlq_length": dlq_length,
                    "groups": group_metrics
                }
            except Exception:
                pass
        return metrics

event_bus = EventBus()
