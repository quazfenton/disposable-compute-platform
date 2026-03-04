"""
Rate Limiting Middleware for disposable compute platform
Prevents API abuse and protects resources
"""
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict
from functools import wraps
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class RateLimitConfig:
    """Configuration for rate limiting"""
    def __init__(
        self,
        max_requests: int = 100,
        window_seconds: int = 60,
        block_duration_seconds: int = 300
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.block_duration_seconds = block_duration_seconds


class RateLimiter:
    """Token bucket rate limiter with IP-based tracking"""
    
    def __init__(self, default_config: RateLimitConfig = None):
        self.default_config = default_config or RateLimitConfig()
        
        # Request tracking: {identifier: [timestamps]}
        self._requests: Dict[str, List[float]] = defaultdict(list)
        
        # Blocked identifiers: {identifier: block_until_timestamp}
        self._blocked: Dict[str, float] = {}
        
        # Rate limit configs per endpoint: {endpoint: config}
        self._endpoint_configs: Dict[str, RateLimitConfig] = {}
        
        logger.info("RateLimiter initialized")
    
    def configure_endpoint(self, endpoint: str, config: RateLimitConfig):
        """Configure rate limit for specific endpoint"""
        self._endpoint_configs[endpoint] = config
        logger.info(f"Configured rate limit for {endpoint}: {config.max_requests} requests per {config.window_seconds}s")
    
    def _get_config(self, endpoint: str) -> RateLimitConfig:
        """Get rate limit config for endpoint"""
        return self._endpoint_configs.get(endpoint, self.default_config)
    
    def _get_identifier(self, request: Request) -> str:
        """Get rate limit identifier for request"""
        # Try to get user ID from auth context first
        user_id = getattr(request.state, 'user_id', None)
        if user_id:
            return f"user:{user_id}"
        
        # Fall back to IP address
        client_ip = request.client.host if request.client else "unknown"
        
        # Check for X-Forwarded-For header (behind proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            client_ip = forwarded_for.split(",")[0].strip()
        
        return f"ip:{client_ip}"
    
    def _clean_old_requests(self, identifier: str, window_seconds: int):
        """Remove requests older than the window"""
        now = time.time()
        cutoff = now - window_seconds
        
        self._requests[identifier] = [
            ts for ts in self._requests[identifier]
            if ts > cutoff
        ]
    
    def is_allowed(self, request: Request) -> tuple[bool, Optional[int]]:
        """
        Check if request is allowed
        
        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        identifier = self._get_identifier(request)
        now = time.time()
        
        # Check if identifier is blocked
        if identifier in self._blocked:
            block_until = self._blocked[identifier]
            if now < block_until:
                retry_after = int(block_until - now)
                logger.warning(f"Rate limit exceeded - {identifier} blocked for {retry_after}s")
                return False, retry_after
            else:
                # Block expired, remove it
                del self._blocked[identifier]
        
        # Get endpoint config
        endpoint = request.url.path
        config = self._get_config(endpoint)
        
        # Clean old requests
        self._clean_old_requests(identifier, config.window_seconds)
        
        # Check if under limit
        current_count = len(self._requests[identifier])
        
        if current_count >= config.max_requests:
            # Calculate retry after
            oldest_request = min(self._requests[identifier])
            retry_after = int(oldest_request + config.window_seconds - now) + 1
            
            # Block if repeatedly exceeding
            if current_count >= config.max_requests * 3:
                self._blocked[identifier] = now + config.block_duration_seconds
                logger.warning(f"Rate limit exceeded repeatedly - {identifier} blocked for {config.block_duration_seconds}s")
                return False, config.block_duration_seconds
            
            logger.warning(f"Rate limit exceeded - {identifier} made {current_count} requests in {config.window_seconds}s")
            return False, retry_after
        
        # Record this request
        self._requests[identifier].append(now)
        
        return True, None
    
    def get_rate_limit_headers(self, request: Request) -> Dict[str, str]:
        """Get rate limit headers for response"""
        identifier = self._get_identifier(request)
        endpoint = request.url.path
        config = self._get_config(endpoint)
        
        # Clean old requests
        self._clean_old_requests(identifier, config.window_seconds)
        
        current_count = len(self._requests[identifier])
        remaining = max(0, config.max_requests - current_count)
        
        # Calculate reset time
        if self._requests[identifier]:
            oldest_request = min(self._requests[identifier])
            reset_time = int(oldest_request + config.window_seconds)
        else:
            reset_time = int(time.time() + config.window_seconds)
        
        return {
            "X-RateLimit-Limit": str(config.max_requests),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_time)
        }
    
    def cleanup(self):
        """Clean up old request data"""
        now = time.time()
        max_window = max(
            config.window_seconds 
            for config in list(self._endpoint_configs.values()) + [self.default_config]
        )
        cutoff = now - (max_window * 2)
        
        # Clean old requests
        for identifier in list(self._requests.keys()):
            self._requests[identifier] = [
                ts for ts in self._requests[identifier]
                if ts > cutoff
            ]
            # Remove empty entries
            if not self._requests[identifier]:
                del self._requests[identifier]
        
        # Clean expired blocks
        for identifier in list(self._blocked.keys()):
            if now >= self._blocked[identifier]:
                del self._blocked[identifier]
        
        logger.debug("Rate limiter cleanup completed")


# Global rate limiter instance
rate_limiter = RateLimiter()


def rate_limit(max_requests: int = 100, window_seconds: int = 60):
    """Decorator for rate limiting endpoints"""
    config = RateLimitConfig(
        max_requests=max_requests,
        window_seconds=window_seconds
    )
    
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # Configure endpoint
            rate_limiter.configure_endpoint(request.url.path, config)
            
            # Check rate limit
            allowed, retry_after = rate_limiter.is_allowed(request)
            
            if not allowed:
                # Get rate limit headers
                headers = rate_limiter.get_rate_limit_headers(request)
                headers["Retry-After"] = str(retry_after)
                
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    headers=headers
                )
            
            # Call the function
            response = await func(request, *args, **kwargs)
            
            # Add rate limit headers to response
            if hasattr(response, 'headers'):
                for key, value in rate_limiter.get_rate_limit_headers(request).items():
                    response.headers[key] = value
            
            return response
        
        return wrapper
    return decorator


async def rate_limit_middleware(request: Request, call_next):
    """Middleware for rate limiting all requests"""
    # Check rate limit
    allowed, retry_after = rate_limiter.is_allowed(request)
    
    if not allowed:
        # Get rate limit headers
        headers = rate_limiter.get_rate_limit_headers(request)
        headers["Retry-After"] = str(retry_after)
        
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": "Rate limit exceeded",
                "detail": f"Too many requests. Try again in {retry_after} seconds.",
                "retry_after": retry_after
            },
            headers=headers
        )
    
    # Process request
    response = await call_next(request)
    
    # Add rate limit headers
    for key, value in rate_limiter.get_rate_limit_headers(request).items():
        response.headers[key] = value
    
    return response


# Pre-configured rate limits for common endpoints
RATE_LIMITS = {
    # Session creation - most critical
    "POST /sessions": RateLimitConfig(max_requests=10, window_seconds=60),
    
    # Session queries
    "GET /sessions": RateLimitConfig(max_requests=60, window_seconds=60),
    "GET /sessions/{session_id}": RateLimitConfig(max_requests=100, window_seconds=60),
    
    # Authentication endpoints - stricter
    "POST /auth/login": RateLimitConfig(max_requests=5, window_seconds=60),
    "POST /auth/register": RateLimitConfig(max_requests=3, window_seconds=60),
    "POST /auth/refresh": RateLimitConfig(max_requests=10, window_seconds=60),
    
    # Logs - expensive operation
    "GET /sessions/{session_id}/logs": RateLimitConfig(max_requests=30, window_seconds=60),
    
    # WebSocket connections
    "WS /ws/logs/{session_id}": RateLimitConfig(max_requests=20, window_seconds=60),
    
    # Health checks - allow more
    "GET /health": RateLimitConfig(max_requests=300, window_seconds=60),
    
    # Default for other endpoints
    "default": RateLimitConfig(max_requests=100, window_seconds=60)
}


def setup_rate_limiting():
    """Setup rate limiting with pre-configured limits"""
    # Configure all endpoints
    for endpoint, config in RATE_LIMITS.items():
        if endpoint != "default":
            rate_limiter.configure_endpoint(endpoint, config)
    
    logger.info("Rate limiting configured with pre-defined limits")
    
    return rate_limiter


class QuotaManager:
    """Manage user quotas based on tier"""
    
    def __init__(self):
        # Quotas per tier
        self.quotas = {
            "free": {
                "sessions_per_hour": 5,
                "sessions_per_day": 20,
                "max_session_ttl": 60,  # minutes
                "max_concurrent_sessions": 3,
                "cpu_cores": 2,
                "memory_mb": 2048,
                "storage_gb": 10
            },
            "pro": {
                "sessions_per_hour": 20,
                "sessions_per_day": 100,
                "max_session_ttl": 480,  # 8 hours
                "max_concurrent_sessions": 10,
                "cpu_cores": 8,
                "memory_mb": 16384,
                "storage_gb": 50
            },
            "enterprise": {
                "sessions_per_hour": 100,
                "sessions_per_day": 500,
                "max_session_ttl": 1440,  # 24 hours
                "max_concurrent_sessions": 50,
                "cpu_cores": 32,
                "memory_mb": 65536,
                "storage_gb": 200
            }
        }
        
        # Usage tracking: {user_id: {metric: count}}
        self._usage: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        
        logger.info("QuotaManager initialized")
    
    def get_quota(self, user_tier: str, metric: str) -> int:
        """Get quota for user tier and metric"""
        tier_quotas = self.quotas.get(user_tier, self.quotas["free"])
        return tier_quotas.get(metric, 0)
    
    def check_quota(self, user_id: str, user_tier: str, metric: str, required: int = 1) -> tuple[bool, int]:
        """
        Check if user has quota remaining
        
        Returns:
            Tuple of (has_quota, remaining)
        """
        limit = self.get_quota(user_tier, metric)
        current = self._usage[user_id][metric]
        remaining = max(0, limit - current)
        
        has_quota = current + required <= limit
        
        if not has_quota:
            logger.warning(f"User {user_id} exceeded quota for {metric}: {current}/{limit}")
        
        return has_quota, remaining
    
    def increment_usage(self, user_id: str, user_tier: str, metric: str, amount: int = 1):
        """Increment user usage"""
        self._usage[user_id][metric] += amount
        logger.debug(f"User {user_id} usage: {metric} = {self._usage[user_id][metric]}")
    
    def reset_usage(self, user_id: str, metric: Optional[str] = None):
        """Reset user usage"""
        if metric:
            self._usage[user_id][metric] = 0
        else:
            self._usage[user_id] = defaultdict(int)
    
    async def cleanup_old_usage(self):
        """Reset usage counters periodically (call every hour)"""
        # This would typically be called by a background task
        for user_id in list(self._usage.keys()):
            # Reset hourly counters
            self._usage[user_id]["sessions_per_hour"] = 0
            
            # Reset daily counters (would need timestamp tracking in production)
            # For now, we'll reset everything
            # In production, track timestamps and reset based on time windows
            pass


# Global quota manager
quota_manager = QuotaManager()


def require_quota(metric: str):
    """Decorator to check user quota before endpoint execution"""
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # Get user from request state (set by auth middleware)
            user = getattr(request.state, 'current_user', None)
            
            if not user:
                # No auth required, allow through
                return await func(*args, **kwargs)
            
            user_id = user.id
            user_tier = user.tier
            
            # Check quota
            has_quota, remaining = quota_manager.check_quota(user_id, user_tier, metric)
            
            if not has_quota:
                limit = quota_manager.get_quota(user_tier, metric)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Quota exceeded for {metric}. Limit: {limit}, Reset: 1 hour"
                )
            
            # Increment usage
            quota_manager.increment_usage(user_id, user_tier, metric)
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator
