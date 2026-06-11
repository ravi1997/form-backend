import pytest
from flask import Flask
from testcontainers.mongodb import MongoDbContainer
from testcontainers.redis import RedisContainer
import mongoengine
import mongomock
from utils.redis_client import redis_client


class _MockRedisPipeline:
    def __init__(self, client):
        self.client = client

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def set(self, *args, **kwargs):
        self.client.set(*args, **kwargs)
        return self

    def execute(self):
        return None


class _MockRedisClient:
    def __init__(self):
        self.store = {}
        self.expiry = {}
        self.queue = []

    def ping(self):
        return True

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        if ex is not None:
            self.expiry[key] = ex
        return True

    def delete(self, *keys):
        deleted = 0
        for key in keys:
            if key in self.store:
                deleted += 1
                self.store.pop(key, None)
                self.expiry.pop(key, None)
        return deleted

    def expire(self, key, ttl):
        if key in self.store:
            self.expiry[key] = ttl
            return True
        return False

    def rpush(self, queue_name, *values):
        self.queue.extend(values)
        return len(self.queue)

    def lpop(self, queue_name):
        if self.queue:
            return self.queue.pop(0)
        return None

    def pipeline(self):
        return _MockRedisPipeline(self)


def _docker_is_available() -> bool:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


DOCKER_AVAILABLE = _docker_is_available()


@pytest.fixture(scope="function")
def app():
    app = Flask("test")
    app.config["JWT_SECRET_KEY"] = "test-secret"
    app.config["JWT_ALGORITHM"] = "HS256"
    from extensions import jwt

    jwt.init_app(app)
    return app


@pytest.fixture(autouse=True)
def app_context(app):
    with app.app_context():
        yield


@pytest.fixture(scope="session")
def mongo_container():
    if not DOCKER_AVAILABLE:
        yield "mongomock"
    else:
        try:
            with MongoDbContainer("mongo:6.0") as mongo:
                yield mongo.get_connection_url()
        except Exception as exc:
            pytest.skip(f"MongoDB test container unavailable: {exc}")


@pytest.fixture(scope="session")
def redis_container():
    if not DOCKER_AVAILABLE:
        yield "mock://redis"
    else:
        try:
            with RedisContainer("redis:7.0-alpine") as redis:
                yield redis.get_connection_url()
        except Exception as exc:
            pytest.skip(f"Redis test container unavailable: {exc}")


@pytest.fixture(scope="function")
def db_connection(mongo_container):
    """Establishes an ephemeral connection to the isolated Mongo instance for testing."""
    try:
        mongoengine.disconnect()
    except Exception:
        pass
    if mongo_container == "mongomock":
        conn = mongoengine.connect(
            "test_db",
            alias="default",
            uuidRepresentation="standard",
            mongo_client_class=mongomock.MongoClient,
        )
    else:
        conn = mongoengine.connect(
            "test_db", host=mongo_container, uuidRepresentation="standard"
        )
    yield
    try:
        conn.drop_database("test_db")
    except Exception:
        pass
    try:
        mongoengine.disconnect()
    except Exception:
        pass


@pytest.fixture(scope="function")
def redis_mock(redis_container):
    """Mocks out the Redis cache client with the test container endpoint."""
    from services.redis_service import redis_service

    mock_client = _MockRedisClient()
    redis_service.cache.client = mock_client
    redis_service.session.client = mock_client
    redis_service.queue.client = mock_client

    def mock_configure_client(name, config):
        pass

    redis_service.configure_client = mock_configure_client

    redis_client.cache = mock_client
    yield redis_client
