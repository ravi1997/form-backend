import pytest
import redis
from services.redis_service import RedisService, RedisConfig, with_retry


@pytest.fixture
def mock_redis_service(monkeypatch):
    """Fixture providing a RedisService with mocked Redis client."""

    class MockRedisClient:
        def __init__(self, *args, **kwargs):
            self.store = {}
            self._queue = []
            self.expires = {}

        def get(self, key):
            return self.store.get(key)

        def set(self, key, value, ex=None):
            self.store[key] = value
            if ex:
                self.expires[key] = ex
            return True

        def delete(self, *keys):
            count = 0
            for k in keys:
                if k in self.store:
                    del self.store[k]
                    count += 1
            return count

        def expire(self, key, ttl):
            if key in self.store:
                self.expires[key] = ttl
                return True
            return False

        def rpush(self, queue_name, *values):
            for v in values:
                self._queue.append(v)
            return len(self._queue)

        def lpop(self, queue_name):
            if self._queue:
                return self._queue.pop(0)
            return None

        def pipeline(self):
            class MockPipeline:
                def __init__(self, client):
                    self.client = client

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

                def set(self, *args, **kwargs):
                    self.client.set(*args, **kwargs)
                    return self

                def execute(self):
                    pass

            return MockPipeline(self)

    # Patch the real Redis class with our mock
    monkeypatch.setattr(redis, "Redis", MockRedisClient)

    # Also patch connection pool to avoid real connections
    class MockPool:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(redis, "ConnectionPool", MockPool)

    service = RedisService()
    # Configure clients for our tests
    service.configure_client("cache", RedisConfig(db=0))
    service.configure_client("session", RedisConfig(db=1))
    service.configure_client("queue", RedisConfig(db=2))

    return service


def test_redis_set_get_cache(mock_redis_service):
    """Test standard SET and GET for cache."""
    cache = mock_redis_service.cache

    # Store string
    assert cache.set("test_key", "test_value") is True
    assert cache.get("test_key") == "test_value"

    # Store dict (auto-serialized to JSON)
    assert cache.set("user:1", {"name": "Alice"}) is True
    assert cache.get("user:1") == {"name": "Alice"}


def test_redis_set_ttl(mock_redis_service):
    """Test SET with TTL expiration."""
    cache = mock_redis_service.cache
    assert cache.set("expiring_key", "value", ttl=60) is True
    assert cache.client.expires.get("expiring_key") == 60


def test_redis_delete(mock_redis_service):
    """Test key deletion."""
    session = mock_redis_service.session
    session.set("sess_123", "data")
    assert session.delete("sess_123") == 1
    assert session.get("sess_123") is None


def test_redis_queue_push_pop(mock_redis_service):
    """Test pushing and popping from queues."""
    queue = mock_redis_service.queue

    assert queue.push("task_queue", {"job": "send_email", "to": "test@test.com"}) == 1

    popped = queue.pop("task_queue")
    assert popped == {"job": "send_email", "to": "test@test.com"}


def test_retry_logic():
    """Test the exponential backoff retry logic."""
    attempts = 0

    class TestException(redis.ConnectionError):
        pass

    @with_retry(max_retries=2, base_delay=0.01)
    def flappy_function():
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise TestException("Connection failed")
        return "success"

    result = flappy_function()
    assert result == "success"
    assert attempts == 3  # Try 1, Try 2, Success on 3


def test_retry_exhaustion():
    """Test exception is raised when retries are exhausted."""
    attempts = 0

    class TestException(redis.ConnectionError):
        pass

    @with_retry(max_retries=2, base_delay=0.01)
    def failing_function():
        nonlocal attempts
        attempts += 1
        raise TestException("Connection forever failed")

    with pytest.raises(TestException):
        failing_function()

    assert attempts == 3  # Try 1, Retry 1, Retry 2 -> Exhausted
