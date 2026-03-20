from config.settings import settings


class RedisConfig:
    """Configuration class for Redis clients."""

    def __init__(
        self,
        host: str = settings.REDIS_HOST,
        port: int = settings.REDIS_PORT,
        db: int = settings.REDIS_DB,
        password: str = settings.REDIS_PASSWORD,
        max_connections: int = 50,
        socket_timeout: int = 10,
        decode_responses: bool = True,
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.max_connections = max_connections
        self.socket_timeout = socket_timeout
        self.decode_responses = decode_responses
