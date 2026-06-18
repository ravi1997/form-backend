from datetime import datetime, timezone
from typing import Dict, Any, Optional
from models.integration import OutboxEvent
from services.event_bus import event_bus
from logger.unified_logger import app_logger, error_logger


class OutboxService:
    def publish_transactionally(
        self,
        topic: str,
        payload: Dict[str, Any],
        organization_id: Optional[str] = None,
    ) -> OutboxEvent:
        """
        Saves the event to the MongoDB OutboxEvent collection.
        Attempts immediate publishing to the Event Bus.
        If publishing succeeds, status is updated to 'published'.
        If publishing fails, status remains 'failed' to be picked up by the background task.
        """
        app_logger.info(
            f"OutboxService: Staging event transactionally for topic={topic}"
        )
        event = OutboxEvent(
            topic=topic,
            payload=payload,
            organization_id=organization_id,
            status="pending",
        )
        event.save()

        try:
            event_bus.publish(topic, payload)
            event.status = "published"
            event.processed_at = datetime.now(timezone.utc)
            event.save()
            app_logger.info(
                f"OutboxService: Event {event.id} published successfully to topic={topic}"
            )
        except Exception as e:
            error_logger.error(
                f"OutboxService: Failed immediate publish for event {event.id} on topic {topic}: {str(e)}",
                exc_info=True,
            )
            event.status = "failed"
            event.error_message = str(e)
            event.save()

        return event

    def process_pending_outbox_events(
        self, max_retries: int = 3
    ) -> Dict[str, int]:
        """
        Queries all pending or failed outbox events and retries publishing them.
        Returns a count of processed and failed retries.
        """
        # Query pending/failed events. Use __raw__ or explicit query because default Tenant filter
        # might block system worker from seeing them.
        events = OutboxEvent.objects(status__in=["pending", "failed"])
        processed_count = 0
        failed_count = 0
        dead_letter_count = 0

        app_logger.info(
            f"OutboxService: Found {len(events)} pending/failed events to process"
        )

        for event in events:
            try:
                event.retry_count += 1
                event_bus.publish(event.topic, event.payload)
                event.status = "published"
                event.processed_at = datetime.now(timezone.utc)
                event.error_message = None
                event.save()
                processed_count += 1
                app_logger.info(
                    f"OutboxService: Retry succeeded for event {event.id} on topic={event.topic}"
                )
            except Exception as e:
                failed_count += 1
                event.error_message = str(e)
                if event.retry_count >= max_retries:
                    # Mark as permanently failed or route to DLQ
                    event.status = "failed"
                    app_logger.error(
                        f"OutboxService: Event {event.id} exceeded max retries. Marking as failed."
                    )
                    dead_letter_count += 1
                else:
                    event.status = "failed"
                event.save()

        return {
            "processed": processed_count,
            "failed": failed_count,
            "dead_lettered": dead_letter_count,
        }


outbox_service = OutboxService()
