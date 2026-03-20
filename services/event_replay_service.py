import json
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta, timezone
from services.redis_service import redis_service
from services.event_bus import event_bus

logger = logging.getLogger(__name__)

class EventReplayService:
    """
    Handles replaying events from Redis Streams to downstream consumers.
    Supports rebuilding analytics, reindexing search data, and retrying failures.
    """

    def replay_stream(self, topic: str, hours: int, organization_id: str = None) -> int:
        """
        Replays events from a given topic for the last X hours.
        Optionally filters by organization_id.
        """
        logger.info(f"Starting replay for topic: {topic} (last {hours}h)")
        
        # Calculate start ID based on timestamp
        start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        start_id = f"{int(start_time.timestamp() * 1000)}-0"
        
        count = 0
        try:
            # Read from the stream without a consumer group to get historical data
            messages = redis_service.cache.client.xrange(topic, min=start_id, max='+')
            
            for message_id, message_data in messages:
                payload_raw = self._message_get(message_data, "payload", "{}")
                if isinstance(payload_raw, bytes):
                    payload_raw = payload_raw.decode("utf-8")
                payload = json.loads(payload_raw or "{}")
                
                # Filter by tenant if provided
                msg_org_raw = self._message_get(message_data, "organization_id", "unknown")
                if isinstance(msg_org_raw, bytes):
                    msg_org_raw = msg_org_raw.decode("utf-8")
                msg_org_id = str(msg_org_raw)
                if organization_id and msg_org_id != organization_id:
                    continue
                
                # Dispatch for specific topic handling
                self._dispatch_replay(topic, payload, msg_org_id)
                count += 1
                
            logger.info(f"Replay completed. Processed {count} messages.")
        except Exception as e:
            logger.error(f"Error during replay of {topic}: {e}", exc_info=True)
            
        return count

    def _dispatch_replay(self, topic: str, payload: Dict[str, Any], organization_id: str):
        """Dispatches replayed events to their respective services/tasks."""
        if topic == "form.submitted":
            # 1. Rebuild Analytics (Trigger worker task)
            from tasks.ai_tasks import async_generate_form_summary
            async_generate_form_summary.delay(payload["form_id"], organization_id)
            
            # 2. Reindex Vector Data
            from tasks.ai_tasks import async_index_response_vector
            async_index_response_vector.delay(payload["response_id"], organization_id)
            
        elif topic == "webhook.failed":
            # 3. Retry Webhook Delivery
            from services.webhook_service import webhook_service
            webhook_service.trigger_webhook(
                payload.get("webhook_id"),
                payload.get("data", {}),
                organization_id=organization_id,
            )

    def retry_dlq(self, topic: str, organization_id: str = None) -> int:
        """Moves messages from DLQ back to the main stream for reprocessing."""
        dlq_topic = f"{topic}:dlq"
        messages = redis_service.cache.client.xrange(dlq_topic)
        count = 0
        
        for message_id, message_data in messages:
            payload_raw = self._message_get(message_data, "payload", "{}")
            if isinstance(payload_raw, bytes):
                payload_raw = payload_raw.decode("utf-8")
            payload = json.loads(payload_raw or "{}")
            msg_org_raw = self._message_get(message_data, "organization_id", "unknown")
            if isinstance(msg_org_raw, bytes):
                msg_org_raw = msg_org_raw.decode("utf-8")
            msg_org_id = str(msg_org_raw)
            if organization_id and msg_org_id != organization_id:
                continue
            
            # Remove the DLQ error before republishing
            if "dlq_error" in payload:
                del payload["dlq_error"]
                
            event_bus.publish(topic, payload)
            redis_service.cache.client.xdel(dlq_topic, message_id)
            count += 1
            
        return count

    @staticmethod
    def _message_get(message_data: dict, key: str, default: Any = None) -> Any:
        if key in message_data:
            return message_data.get(key, default)
        b_key = key.encode("utf-8")
        if b_key in message_data:
            return message_data.get(b_key, default)
        return default

event_replay_service = EventReplayService()
