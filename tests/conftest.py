import pytest
from testcontainers.mongodb import MongoDbContainer
from testcontainers.redis import RedisContainer
import mongoengine
from utils.redis_client import redis_client

@pytest.fixture(scope="session")
def mongo_container():
    with MongoDbContainer("mongo:6.0") as mongo:
        yield mongo.get_connection_url()

@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("redis:7.0-alpine") as redis:
        yield redis.get_connection_url()

@pytest.fixture(scope="function")
def db_connection(mongo_container):
    """Establishes an ephemeral connection to the isolated Mongo instance for testing."""
    mongoengine.connect("test_db", host=mongo_container)
    yield
    mongoengine.disconnect()

@pytest.fixture(scope="function")
def redis_mock(redis_container):
    """Mocks out the Redis cache client with the test container endpoint."""
    import redis
    redis_client.cache = redis.from_url(redis_container)
    yield redis_client
