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
        pytest.skip("Docker daemon is unavailable; skipping MongoDB-backed tests")
    try:
        with MongoDbContainer("mongo:6.0") as mongo:
            yield mongo.get_connection_url()
    except Exception as exc:
        pytest.skip(f"MongoDB test container unavailable: {exc}")


@pytest.fixture(scope="session")
def redis_container():
    if not DOCKER_AVAILABLE:
        pytest.skip("Docker daemon is unavailable; skipping Redis-backed tests")
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
    mongoengine.connect("test_db", host=mongo_container)
    yield
    try:
        mongoengine.disconnect()
    except Exception:
        pass


@pytest.fixture(scope="function")
def redis_mock(redis_container):
    """Mocks out the Redis cache client with the test container endpoint."""
    import redis

    redis_client.cache = redis.from_url(redis_container)
    yield redis_client
