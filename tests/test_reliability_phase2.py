import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import json
import mongomock
import mongoengine
import sys

from models.OutboxEvent import OutboxEvent
from models.DeadLetterTask import DeadLetterTask
from services.outbox_service import outbox_service
from services.notification_service import NotificationObservability
from utils.idempotency import celery_idempotent
import config.celery
from config.celery import celery_app, ReliabilityTask


# Establish in-memory mongomock database
@pytest.fixture(autouse=True)
def mock_db():
    try:
        mongoengine.disconnect()
    except Exception:
        pass
    conn = mongoengine.connect(
        "test_db", mongo_client_class=mongomock.MongoClient
    )
    yield conn
    try:
        mongoengine.disconnect()
    except Exception:
        pass


# Establish mock redis client in extensions and utils.idempotency
@pytest.fixture(autouse=True)
def mock_redis():
    import extensions
    import utils.idempotency
    
    original_client = extensions.redis_client
    mock = MagicMock()
    storage = {}
    
    def mock_get(key):
        val = storage.get(key)
        sys.stderr.write(f"\n[DEBUG REDIS GET] key={key}, val={val}\n")
        return val
        
    def mock_setex(key, ttl, value):
        sys.stderr.write(f"\n[DEBUG REDIS SETEX] key={key}, val={value}\n")
        storage[key] = value
        
    def mock_delete(key):
        sys.stderr.write(f"\n[DEBUG REDIS DEL] key={key}\n")
        storage.pop(key, None)
        
    mock.get.side_effect = mock_get
    mock.setex.side_effect = mock_setex
    mock.delete.side_effect = mock_delete
    
    extensions.redis_client = mock
    utils.idempotency.redis_client = mock
    
    yield mock
    
    extensions.redis_client = original_client
    utils.idempotency.redis_client = original_client


# Dummy task to test idempotency directly
@celery_idempotent(ttl_seconds=10)
def dummy_idempotent_task(self, x, y):
    dummy_idempotent_task.execution_count = getattr(dummy_idempotent_task, "execution_count", 0) + 1
    return x + y


def test_outbox_publish_and_process():
    """Test staging and processing of outbox events using mongomock."""
    payload = {"form_id": "test-form-123", "data": "value"}
    topic = "form.submitted"
    
    with patch("services.outbox_service.event_bus.publish") as mock_publish:
        # 1. Test publish_transactionally
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
        mock_publish.assert_called_once_with(topic, payload)

        # 2. Stage a failed event manually
        failed_event = OutboxEvent(
            topic="tenant.key.rotated",
            payload={"key_id": "key-123"},
            organization_id="org-abc",
            status="failed"
        )
        failed_event.save()

        mock_publish.reset_mock()
        
        # Verify we can process the failed event
        report = outbox_service.process_pending_outbox_events()
        assert report["processed"] == 1
        assert report["failed"] == 0
        
        failed_event.reload()
        assert failed_event.status == "published"
        assert failed_event.processed_at is not None
        mock_publish.assert_called_once_with("tenant.key.rotated", {"key_id": "key-123"})


def test_celery_task_idempotency(mock_redis):
    """Test that celery_idempotent decorator replays cached result and avoids duplicate execution."""
    dummy_idempotent_task.execution_count = 0
    
    # First execution (not cached)
    res1 = dummy_idempotent_task(None, 10, 20, idempotency_key="unique-test-key")
    assert res1 == 30
    assert dummy_idempotent_task.execution_count == 1
    
    # Second execution with same key (should be replayed from mock redis)
    mock_redis.setex("idempotency:celery:dummy_idempotent_task:unique-test-key", 10, json.dumps({"status": "completed", "result": 30}))
    res2 = dummy_idempotent_task(None, 10, 20, idempotency_key="unique-test-key")
    assert res2 == 30
    assert dummy_idempotent_task.execution_count == 1  # Execution count should not have increased


def test_dead_letter_task_logging():
    """Test that ReliabilityTask logs failed tasks to MongoDB DeadLetterTask when retries are exhausted."""
    class DummyFailedTask(ReliabilityTask):
        name = "tasks.test_dummy_failed"
        max_retries = 3
        
        def __init__(self):
            self._mock_request = MagicMock()
            self._mock_request.retries = 3
            self._mock_request.headers = {"organization_id": "test-org"}
            
        @property
        def request(self):
            return self._mock_request
    
    task_instance = DummyFailedTask()
    exc = Exception("Permanent Connection Failure")
    
    with patch("celery.app.task.Task.on_failure") as mock_celery_on_failure, \
         patch("logger.unified_logger.error_logger.critical") as mock_critical:
         
        task_instance.on_failure(
            exc=exc,
            task_id="dlq-task-id-abc",
            args=(1, 2),
            kwargs={"foo": "bar"},
            einfo="Traceback details..."
        )
        
        if mock_critical.called:
            sys.stderr.write(f"\n[DEBUG CELERY ERROR] {mock_critical.call_args_list}\n")
            
        # Ensure it saves the record in db
        dlq_record = DeadLetterTask.objects(task_id="dlq-task-id-abc").first()
        assert dlq_record is not None
        assert dlq_record.task_name == "tasks.test_dummy_failed"
        assert dlq_record.args == [1, 2]
        assert dlq_record.kwargs == {"foo": "bar"}
        assert dlq_record.exception == "Permanent Connection Failure"
        assert dlq_record.organization_id == "test-org"


def test_notification_observability_metrics(mock_redis):
    """Test that NotificationObservability successfully tracks webhook metrics."""
    mock_redis.incr.reset_mock()
    
    NotificationObservability.increment_attempt("webhook")
    NotificationObservability.increment_success("webhook")
    NotificationObservability.increment_failure("webhook")
    NotificationObservability.increment_retry("webhook")
    
    assert mock_redis.incr.call_count == 8  # 4 global counters + 4 specific counters
    
    mock_redis.mget.return_value = ["10", "8", "2", "1"]
    metrics = NotificationObservability.get_metrics()
    assert metrics["total_attempts"] == 10
    assert metrics["success"] == 8
    assert metrics["failed"] == 2
    assert metrics["retries"] == 1
