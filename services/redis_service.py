import json
import time
from typing import Any, Dict, Optional
from functools import wraps
import redis
from config.redis import RedisConfig
from logger.unified_logger import app_logger, error_logger, audit_logger

def with_retry(max_retries: int = 3, base_delay: float = 0.1, max_delay: float = 2.0):
    """Decorator to retry Redis operations with exponential backoff on connection errors."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            delay = base_delay
            while True:
                try:
                    return func(*args, **kwargs)
                except (redis.ConnectionError, redis.TimeoutError) as e:
                    retries += 1
                    if retries > max_retries:
                        error_logger.error(
                            f"Redis operation '{func.__name__}' failed after {max_retries} retries: {e}"
                        )
                        raise
                    app_logger.warning(
                        f"Redis connection issue, retrying {retries}/{max_retries} in {delay}s: {e}"
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, max_delay)
                except Exception as e:
                    error_logger.error(f"Unexpected Redis error in '{func.__name__}': {str(e)}", exc_info=True)
                    raise

        return wrapper

    return decorator


class RedisClientProxy:
    """A proxy abstracting basic Redis operations for a specific use case (e.g., cache, session)."""

    def __init__(self, name: str, pool: redis.ConnectionPool):
        self.name = name
        self.client = redis.Redis(connection_pool=pool)

    @with_retry()
    def ping(self) -> bool:
        """Check connection health."""
        app_logger.debug(f"[{self.name}] PING Redis")
        return self.client.ping()

    @with_retry()
    def get(self, key: str) -> Optional[Any]:
        """Retrieve a value by key. Auto-decodes JSON where applicable."""
        start = time.time()
        app_logger.debug(f"[{self.name}] GET key: '{key}'")
        val = self.client.get(key)
        elapsed = (time.time() - start) * 1000
        if val is None:
            app_logger.info(f"[{self.name}] GET miss for key: '{key}' ({elapsed:.2f}ms)")
            return None

        app_logger.debug(f"[{self.name}] GET hit for key: '{key}' ({elapsed:.2f}ms)")

        if isinstance(val, (str, bytes)):
            if isinstance(val, bytes):
                val = val.decode("utf-8")
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                pass
        return val

    @with_retry()
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Store a value with an optional expiration time in seconds."""
        start = time.time()
        app_logger.debug(f"[{self.name}] SET key: '{key}', ttl: {ttl}")
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        elif hasattr(value, "model_dump"):
            value = json.dumps(value.model_dump())

        res = self.client.set(key, value, ex=ttl)
        elapsed = (time.time() - start) * 1000
        app_logger.info(f"[{self.name}] SET key: '{key}', ttl: {ttl} ({elapsed:.2f}ms)")
        return res

    @with_retry()
    def delete(self, *keys: str) -> int:
        """Delete one or more keys."""
        start = time.time()
        app_logger.debug(f"[{self.name}] DEL keys: {keys}")
        res = self.client.delete(*keys)
        elapsed = (time.time() - start) * 1000
        app_logger.info(f"[{self.name}] DEL keys: {keys}, deleted: {res} ({elapsed:.2f}ms)")
        return res

    @with_retry()
    def expire(self, key: str, ttl: int) -> bool:
        """Set a time-to-live on an existing key."""
        start = time.time()
        app_logger.debug(f"[{self.name}] EXPIRE key: '{key}', ttl: {ttl}")
        res = self.client.expire(key, ttl)
        elapsed = (time.time() - start) * 1000
        app_logger.info(f"[{self.name}] EXPIRE key: '{key}', ttl: {ttl} ({elapsed:.2f}ms)")
        return res

    @with_retry()
    def push(self, queue_name: str, data: Any) -> int:
        """Push a value onto a list/queue."""
        start = time.time()
        app_logger.debug(f"[{self.name}] PUSH queue: '{queue_name}'")
        if isinstance(data, (dict, list)):
            data = json.dumps(data)
        elif hasattr(data, "model_dump"):
            data = json.dumps(data.model_dump())
        res = self.client.rpush(queue_name, data)
        elapsed = (time.time() - start) * 1000
        app_logger.info(f"[{self.name}] PUSH queue: '{queue_name}' ({elapsed:.2f}ms)")
        return res

    @with_retry()
    def pop(self, queue_name: str) -> Optional[Any]:
        """Pop a value from a list/queue."""
        start = time.time()
        app_logger.debug(f"[{self.name}] POP queue: '{queue_name}'")
        val = self.client.lpop(queue_name)
        elapsed = (time.time() - start) * 1000
        app_logger.debug(f"[{self.name}] POP queue: '{queue_name}' ({elapsed:.2f}ms)")

        if val is not None:
            if isinstance(val, bytes):
                val = val.decode("utf-8")
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                pass
        return val

    def pipeline(self):
        """Returns a Redis pipeline for batched operations."""
        app_logger.debug(f"[{self.name}] Creating pipeline")
        return self.client.pipeline()


class RedisService:
    """Unified Redis Service orchestrating multiple Redis clients."""

    def __init__(self):
        self._pools: Dict[str, redis.ConnectionPool] = {}
        self._clients: Dict[str, RedisClientProxy] = {}

    def configure_client(self, name: str, config: RedisConfig):
        """Configure and register a Redis client by name."""
        app_logger.info(f"Configuring Redis client '{name}'")
        try:
            pool = redis.ConnectionPool(
                host=config.host,
                port=config.port,
                db=config.db,
                password=config.password,
                max_connections=config.max_connections,
                socket_timeout=config.socket_timeout,
                decode_responses=config.decode_responses,
            )
            self._pools[name] = pool
            self._clients[name] = RedisClientProxy(name, pool)
            audit_logger.info(
                f"Configured Redis client '{name}' at {config.host}:{config.port} (db={config.db})"
            )
        except Exception as e:
            error_logger.error(f"Failed to configure Redis client '{name}': {str(e)}")
            raise

    def get_client(self, name: str) -> RedisClientProxy:
        """Fetch a configured Redis client proxy."""
        if name not in self._clients:
            app_logger.warning(
                f"Client '{name}' not found. Initializing with default config."
            )
            self.configure_client(name, RedisConfig())
        return self._clients[name]

    @property
    def cache(self) -> RedisClientProxy:
        return self.get_client("cache")

    @property
    def session(self) -> RedisClientProxy:
        return self.get_client("session")

    @property
    def queue(self) -> RedisClientProxy:
        return self.get_client("queue")


# Expose a singleton instance representing the service
redis_service = RedisService()
