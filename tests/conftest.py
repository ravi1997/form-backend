import pytest
from flask import Flask
from testcontainers.mongodb import MongoDbContainer
from testcontainers.redis import RedisContainer
import mongoengine
from utils.redis_client import redis_client


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
        import os
        uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/form_backend")
        if "form_backend" in uri:
            uri = uri.replace("form_backend", "test_db")
        else:
            uri = uri.replace("27017/", "27017/test_db")
        yield uri
    else:
        try:
            with MongoDbContainer("mongo:6.0") as mongo:
                yield mongo.get_connection_url()
        except Exception as exc:
            pytest.skip(f"MongoDB test container unavailable: {exc}")


@pytest.fixture(scope="session")
def redis_container():
    if not DOCKER_AVAILABLE:
        import os
        host = os.environ.get("REDIS_HOST", "shared-redis")
        port = os.environ.get("REDIS_PORT", "6379")
        password = os.environ.get("REDIS_PASSWORD", "")
        if password:
            uri = f"redis://:{password}@{host}:{port}/15"
        else:
            uri = f"redis://{host}:{port}/15"
        yield uri
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
    conn = mongoengine.connect("test_db", host=mongo_container, uuidRepresentation="standard")
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
    import redis
    from services.redis_service import redis_service

    # Configure redis_service client proxies with mock client
    mock_client = redis.from_url(redis_container)
    
    # Override client proxies in redis_service
    redis_service.cache.client = mock_client
    redis_service.session.client = mock_client
    redis_service.queue.client = mock_client

    # Prevent configure_client from overwriting our mocked clients on app startup
    def mock_configure_client(name, config):
        pass
    redis_service.configure_client = mock_configure_client

    redis_client.cache = mock_client
    yield redis_client
    try:
        mock_client.flushdb()
    except Exception:
        pass


