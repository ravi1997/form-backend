import redis
import os
import logging

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)


class RedisClient:
    def __init__(self):
        try:
            self.client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=True,
            )
            self.client.ping()
            logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.client = None

    def get(self, key):
        if not self.client:
            return None
        return self.client.get(key)

    def set(self, key, value, ex=None):
        if not self.client:
            return False
        return self.client.set(key, value, ex=ex)

    def delete(self, key):
        if not self.client:
            return False
        return self.client.delete(key)

    def exists(self, key):
        if not self.client:
            return False
        return self.client.exists(key)


redis_client = RedisClient()
