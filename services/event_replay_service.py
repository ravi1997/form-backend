import json
from typing import Dict, Any, List
from datetime import datetime, timedelta, timezone
from services.redis_service import redis_service
from services.event_bus import event_bus
from logger.unified_logger import app_logger, error_logger, audit_logger

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
        app_logger.info(f"Initiating stream replay for topic: {topic}, hours: {hours}, org: {organization_id}")
        audit_logger.info(f"Stream replay triggered: topic={topic}, hours={hours}, org_id={organization_id}")
        
        # Calculate start ID based on timestamp
        start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        start_id = f"{int(start_time.timestamp() * 1000)}-0"
        
        count = 0
        try:
            # Read from the stream without a consumer group to get historical data
            messages = redis_service.cache.client.xrange(topic, min=start_id, max='+')
            app_logger.debug(f"Found {len(messages) if messages else 0} messages in range for replay")
            
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
                
            app_logger.info(f"Replay completed for {topic}. Processed {count} messages.")
        except Exception as e:
            error_logger.error(f"Error during replay of {topic}: {str(e)}", exc_info=True)
            
        return count

    def _dispatch_replay(self, topic: str, payload: Dict[str, Any], organization_id: str):
        """Dispatches replayed events to their respective services/tasks."""
        app_logger.debug(f"Dispatching replayed event for topic: {topic}")
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
        app_logger.info(f"Processing DLQ retry for topic: {topic}, org: {organization_id}")
        audit_logger.info(f"DLQ retry triggered: topic={topic}, org_id={organization_id}")
        
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
                
            app_logger.info(f"Republishing message {message_id} from DLQ to {topic}")
            event_bus.publish(topic, payload)
            redis_service.cache.client.xdel(dlq_topic, message_id)
            count += 1
            
        app_logger.info(f"DLQ retry completed for {topic}. Reprocessed {count} messages.")
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
