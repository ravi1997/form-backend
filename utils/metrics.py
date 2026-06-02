import time
from typing import Dict
from services.redis_service import redis_service


class RedisMetricsCollector:
    """
    Performance-optimized metrics collector leveraging the shared Redis cache db (DB 0).
    Tracks API request count, status codes, and latency metrics.
    """

    @staticmethod
    def record_request(path: str, method: str, status_code: int, latency_ms: float):
        try:
            client = redis_service.cache.client
            # Track request counts by method, path, and HTTP status
            count_key = f"metrics:requests:{method}:{path}:{status_code}"
            client.incr(count_key)

            # Track aggregate latency (sum and count) to compute moving averages
            latency_sum_key = f"metrics:latency:sum:{method}:{path}"
            latency_count_key = f"metrics:latency:count:{method}:{path}"

            client.incrbyfloat(latency_sum_key, latency_ms)
            client.incr(latency_count_key)
        except Exception:
            pass

    @staticmethod
    def get_metrics() -> Dict[str, any]:
        """Retrieves aggregated metrics stats."""
        try:
            client = redis_service.cache.client
            keys = client.keys("metrics:*")
            metrics_data = {}
            for key in keys:
                val = client.get(key)
                if val is not None:
                    # Convert to float or int
                    val_str = val.decode("utf-8") if isinstance(val, bytes) else str(val)
                    metrics_data[key] = float(val_str) if "." in val_str else int(val_str)
            return metrics_data
        except Exception:
            return {}
