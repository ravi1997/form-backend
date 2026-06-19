"""
middleware/rate_limiter.py
Rate limiting middleware for API endpoints.
"""

from flask import request, jsonify, g
from functools import wraps
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from redis import Redis
import time
import json
from datetime import datetime, timedelta
from logger.unified_logger import app_logger, error_logger

# Initialize Redis connection
from services.redis_service import redis_service

class RateLimiter:
    """Rate limiting service for API endpoints."""
    
    def __init__(self):
        self.redis = redis_service().cache
        self.default_limits = {
            "unauthenticated": "20 per minute",
            "authenticated": "60 per minute",
            "api_key": "1000 per hour"
        }
    
    def init_app(self, app):
        """Initialize the rate limiter with the Flask app."""
        # Store app reference if needed
        self.app = app
        # Could register rate limit endpoints or other app-specific setup here
        return self
    
    def get_key(self, identifier, endpoint=None):
        """Generate a rate limit key."""
        key = f"rate_limit:{identifier}"
        if endpoint:
            key = f"{key}:{endpoint}"
        return key
    
    def check_rate_limit(self, identifier, limit_string, endpoint=None):
        """Check if the identifier is within rate limits."""
        # Parse limit string (e.g., "100 per hour")
        parts = limit_string.split()
        if len(parts) != 3 or parts[1] != "per":
            raise ValueError(f"Invalid limit format: {limit_string}")
        
        limit_count = int(parts[0])
        period = parts[2].lower()
        
        # Convert period to seconds
        if period == "second":
            window_seconds = 1
        elif period == "minute":
            window_seconds = 60
        elif period == "hour":
            window_seconds = 3600
        elif period == "day":
            window_seconds = 86400
        else:
            raise ValueError(f"Invalid period: {period}")
        
        # Generate Redis key
        key = self.get_key(identifier, endpoint)
        
        # Use Redis pipeline for atomic operations
        pipe = self.redis.pipeline()
        
        # Get current count and set expiration if not exists
        pipe.incr(key)
        pipe.expire(key, window_seconds)
        
        results = pipe.execute()
        current_count = results[0]
        
        # Calculate remaining requests and reset time
        remaining = max(0, limit_count - current_count)
        reset_time = int(time.time() + window_seconds)
        
        return {
            "within_limit": current_count <= limit_count,
            "current_count": current_count,
            "limit": limit_count,
            "remaining": remaining,
            "reset_time": reset_time,
            "window_seconds": window_seconds
        }
    
    def get_api_key_rate_limit(self, api_key):
        """Get rate limit for an API key."""
        from models.oauth import EnhancedApiKey
        
        key = EnhancedApiKey.objects(key_hash=api_key, is_active=True).first()
        if key and key.rate_limit:
            return f"{key.rate_limit.requests_per_period} per {key.rate_limit.period}"
        
        return self.default_limits["api_key"]
    
    def log_rate_limit_event(self, identifier, endpoint, limit_result):
        """Log rate limit events for analytics."""
        try:
            log_data = {
                "identifier": identifier,
                "endpoint": endpoint,
                "timestamp": datetime.utcnow().isoformat(),
                "limit": limit_result["limit"],
                "current_count": limit_result["current_count"],
                "remaining": limit_result["remaining"],
                "within_limit": limit_result["within_limit"]
            }
            
            # Store in Redis with TTL
            log_key = f"rate_limit_log:{identifier}:{int(time.time())}"
            self.redis.setex(log_key, 86400, json.dumps(log_data))  # Keep for 24 hours
            
        except Exception as e:
            error_logger.error(f"Error logging rate limit event: {e}")
    
    def get_rate_limit_headers(self, limit_result):
        """Generate rate limit headers."""
        return {
            "X-RateLimit-Limit": str(limit_result["limit"]),
            "X-RateLimit-Remaining": str(limit_result["remaining"]),
            "X-RateLimit-Reset": str(limit_result["reset_time"]),
            "X-RateLimit-Window": str(limit_result["window_seconds"])
        }

# Global rate limiter instance
rate_limiter = RateLimiter()

def rate_limit(limit_string=None, key_func=None):
    """
    Rate limiting decorator for Flask routes.
    
    Args:
        limit_string: Rate limit string (e.g., "100 per hour")
        key_func: Function to generate rate limit key
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get identifier for rate limiting
            if key_func:
                identifier = key_func()
            else:
                # Default to IP address
                identifier = get_remote_address()
            
            # Determine limit
            if limit_string:
                limit = limit_string
            else:
                # Check for API key in headers
                api_key = request.headers.get('X-API-Key') or request.headers.get('Authorization')
                if api_key:
                    limit = rate_limiter.get_api_key_rate_limit(api_key)
                else:
                    # Check if user is authenticated
                    if hasattr(g, 'current_user') and g.current_user:
                        limit = rate_limiter.default_limits["authenticated"]
                    else:
                        limit = rate_limiter.default_limits["unauthenticated"]
            
            # Check rate limit
            endpoint = request.endpoint
            limit_result = rate_limiter.check_rate_limit(identifier, limit, endpoint)
            
            # Log event
            rate_limiter.log_rate_limit_event(identifier, endpoint, limit_result)
            
            # Add rate limit headers to response
            g.rate_limit_headers = rate_limiter.get_rate_limit_headers(limit_result)
            
            # Check if limit exceeded
            if not limit_result["within_limit"]:
                error_logger.warning(f"Rate limit exceeded for {identifier} on {endpoint}")
                response = jsonify({
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Rate limit exceeded",
                        "details": {
                            "limit": limit_result["limit"],
                            "window": limit_result["window_seconds"],
                            "retry_after": limit_result["window_seconds"]
                        }
                    }
                })
                response.status_code = 429
                
                # Add rate limit headers to error response
                for header, value in g.rate_limit_headers.items():
                    response.headers[header] = value
                
                return response
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def api_key_rate_limit(f):
    """Decorator for API key rate limiting."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get API key from headers
        api_key = None
        auth_header = request.headers.get('Authorization', '')
        
        if auth_header.startswith('Bearer '):
            api_key = auth_header[7:]
        elif request.headers.get('X-API-Key'):
            api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            from utils.response_helper import error_response
            return error_response("API key required", status_code=401)
        
        # Validate API key
        from services.oauth_service import oauth_service
        key_info = oauth_service.validate_api_key(api_key)
        
        if not key_info:
            from utils.response_helper import error_response
            return error_response("Invalid API key", status_code=401)
        
        # Set API key info in context
        g.api_key_info = key_info
        
        # Apply rate limiting
        limit = rate_limiter.get_api_key_rate_limit(api_key)
        identifier = f"api_key:{key_info['key_id']}"
        
        endpoint = request.endpoint
        limit_result = rate_limiter.check_rate_limit(identifier, limit, endpoint)
        
        # Log event
        rate_limiter.log_rate_limit_event(identifier, endpoint, limit_result)
        
        # Add rate limit headers to response
        g.rate_limit_headers = rate_limiter.get_rate_limit_headers(limit_result)
        
        # Check if limit exceeded
        if not limit_result["within_limit"]:
            error_logger.warning(f"API key rate limit exceeded for {key_info['key_id']} on {endpoint}")
            from utils.response_helper import error_response
            response = error_response(
                "Rate limit exceeded",
                status_code=429,
                error_code="RATE_LIMIT_EXCEEDED",
                details={
                    "limit": limit_result["limit"],
                    "window": limit_result["window_seconds"],
                    "retry_after": limit_result["window_seconds"]
                }
            )
            
            # Add rate limit headers to error response
            for header, value in g.rate_limit_headers.items():
                response.headers[header] = value
            
            return response
        
        # Log API key usage
        try:
            from models.oauth import ApiKeyUsageLog
            usage_log = ApiKeyUsageLog(
                api_key_id=key_info['key_id'],
                endpoint=endpoint,
                method=request.method,
                ip_address=get_remote_address(),
                user_agent=request.headers.get('User-Agent', ''),
                timestamp=datetime.utcnow()
            )
            usage_log.save()
        except Exception as e:
            error_logger.error(f"Error logging API key usage: {e}")
        
        return f(*args, **kwargs)
    return decorated_function

def add_rate_limit_headers(response):
    """Add rate limit headers to Flask response."""
    if hasattr(g, 'rate_limit_headers'):
        for header, value in g.rate_limit_headers.items():
            response.headers[header] = value
    return response

def get_rate_limit_stats(identifier, days=7):
    """Get rate limit statistics for an identifier."""
    try:
        # Get rate limit logs from Redis
        keys = rate_limiter.redis.keys(f"rate_limit_log:{identifier}:*")
        
        if not keys:
            return {
                "total_requests": 0,
                "blocked_requests": 0,
                "success_rate": 0,
                "endpoint_stats": {}
            }
        
        # Get log data
        pipe = rate_limiter.redis.pipeline()
        for key in keys:
            pipe.get(key)
        log_data_list = pipe.execute()
        
        # Parse logs
        logs = []
        for log_data in log_data_list:
            if log_data:
                logs.append(json.loads(log_data))
        
        # Filter by time period
        from datetime import datetime, timedelta
        cutoff_time = datetime.utcnow() - timedelta(days=days)
        
        recent_logs = [
            log for log in logs
            if datetime.fromisoformat(log['timestamp']) >= cutoff_time
        ]
        
        # Calculate statistics
        total_requests = len(recent_logs)
        blocked_requests = sum(1 for log in recent_logs if not log['within_limit'])
        success_rate = ((total_requests - blocked_requests) / total_requests * 100) if total_requests > 0 else 0
        
        # Group by endpoint
        endpoint_stats = {}
        for log in recent_logs:
            endpoint = log.get('endpoint', 'unknown')
            if endpoint not in endpoint_stats:
                endpoint_stats[endpoint] = {
                    "requests": 0,
                    "blocked": 0
                }
            
            endpoint_stats[endpoint]["requests"] += 1
            if not log['within_limit']:
                endpoint_stats[endpoint]["blocked"] += 1
        
        return {
            "total_requests": total_requests,
            "blocked_requests": blocked_requests,
            "success_rate": round(success_rate, 2),
            "endpoint_stats": endpoint_stats,
            "period_days": days
        }
        
    except Exception as e:
        error_logger.error(f"Error getting rate limit stats: {e}")
        return {
            "total_requests": 0,
            "blocked_requests": 0,
            "success_rate": 0,
            "endpoint_stats": {},
            "error": str(e)
        }