import functools
import time
from logger import get_logger

sla_logger = get_logger("sla_monitor")

def enforce_sla(max_ms: int):
    """
    Strict Latency Boundary Decorator.
    Emits a high-priority warning if the bounded function execution exceeds `max_ms`.
    Essential for tracing undetected N+1 queries or provider hangs.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = func(*args, **kwargs)
            duration_ms = (time.perf_counter() - start) * 1000
            
            if duration_ms > max_ms:
                sla_logger.warning(
                    f"SLA BREACH 🚨: {func.__module__}.{func.__name__} required {duration_ms:.2f}ms "
                    f"(Threshold: {max_ms}ms)"
                )
            
            return result
        return wrapper
    return decorator
