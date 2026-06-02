import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import json

from models.OutboxEvent import OutboxEvent
from models.DeadLetterTask import DeadLetterTask
from services.outbox_service import outbox_service
from services.notification_service import NotificationObservability
from utils.idempotency import celery_idempotent
from config.celery import celery_app, ReliabilityTask


# Dummy task to test idempotency
@celery_app.task(bind=True)
@celery_idempotent(ttl_seconds=10)
def dummy_idempotent_task(self, x, y):
    dummy_idempotent_task.execution_count = getattr(dummy_idempotent_task, "execution_count", 0) + 1
    return x + y


def test_outbox_publish_and_process(db_connection, redis_mock):
    """Test staging and processing of outbox events."""
    payload = {"form_id": "test-form-123", "data": "value"}
    topic = "form.submitted"
    
    # 1. Publish transactionally (stages event)
    event = outbox_service.publish_transactionally(
        topic=topic,
        payload=payload,
        organization_id="org-abc"
    )
    
    assert event.id is not None
    assert event.status == "published"
    assert event.topic == topic
    assert event.payload == payload
    assert event.organization_id == "org-abc"
    
    # 2. Stage a failed event manually
    failed_event = OutboxEvent(
        topic="tenant.key.rotated",
        payload={"key_id": "key-123"},
        organization_id="org-abc",
        status="failed"
    )
    failed_event.save()
    
    # Verify we can process the failed event
    report = outbox_service.process_pending_outbox_events()
    assert report["processed"] == 1
    
    failed_event.reload()
    assert failed_event.status == "published"
    assert failed_event.processed_at is not None


def test_celery_task_idempotency(db_connection, redis_mock):
    """Test that celery_idempotent decorator replays cached result and avoids duplicate execution."""
    dummy_idempotent_task.execution_count = 0
    
    # First execution
    res1 = dummy_idempotent_task(10, 20, idempotency_key="unique-test-key")
    assert res1 == 30
    assert dummy_idempotent_task.execution_count == 1
    
    # Second execution with same key should be replayed
    res2 = dummy_idempotent_task(10, 20, idempotency_key="unique-test-key")
    assert res2 == 30
    assert dummy_idempotent_task.execution_count == 1  # Should not have incremented


def test_dead_letter_task_logging(db_connection):
    """Test that ReliabilityTask logs failed tasks to MongoDB DeadLetterTask when retries are exhausted."""
    # Create a mock task instance of ReliabilityTask
    class DummyFailedTask(ReliabilityTask):
        name = "tasks.test_dummy_failed"
        max_retries = 3
    
    task_instance = DummyFailedTask()
    # Mock the request retries to be at the maximum limit (i.e. final failure)
    task_instance.request = MagicMock()
    task_instance.request.retries = 3
    task_instance.request.headers = {"organization_id": "test-org"}
    
    exc = Exception("Permanent Connection Failure")
    
    # Call on_failure handler
    task_instance.on_failure(
        exc=exc,
        task_id="dlq-task-id-abc",
        args=(1, 2),
        kwargs={"foo": "bar"},
        einfo="Traceback details..."
    )
    
    # Check DeadLetterTask was created in MongoDB
    dlq_record = DeadLetterTask.objects(task_id="dlq-task-id-abc").first()
    assert dlq_record is not None
    assert dlq_record.task_name == "tasks.test_dummy_failed"
    assert dlq_record.args == [1, 2]
    assert dlq_record.kwargs == {"foo": "bar"}
    assert dlq_record.exception == "Permanent Connection Failure"
    assert dlq_record.organization_id == "test-org"


def test_notification_observability_metrics(redis_mock):
    """Test that NotificationObservability successfully tracks webhook metrics in Redis."""
    # Reset metrics first
    from extensions import redis_client
    redis_client.delete("notification:metrics:total_attempts")
    redis_client.delete("notification:metrics:success")
    redis_client.delete("notification:metrics:failed")
    redis_client.delete("notification:metrics:retries")
    
    NotificationObservability.increment_attempt("webhook")
    NotificationObservability.increment_success("webhook")
    NotificationObservability.increment_failure("webhook")
    NotificationObservability.increment_retry("webhook")
    
    metrics = NotificationObservability.get_metrics()
    assert metrics["total_attempts"] == 1
    assert metrics["success"] == 1
    assert metrics["failed"] == 1
    assert metrics["retries"] == 1
