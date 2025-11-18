import time
import asyncio
from typing import Dict
from dataclasses import dataclass
from .redis_cache import redis_cache


@dataclass
class TokenBucket:
    capacity: int
    refill_rate: float
    tokens: float
    last_refill: float


class WebSocketRateLimiter:
    def __init__(self):
        self.buckets: Dict[str, TokenBucket] = {}
        self.capacity = 10  # 10 pixels per second
        self.refill_rate = 10.0  # 10 tokens per second
        self.burst_capacity = 20  # Allow burst up to 20 pixels
    
    async def check_rate_limit(self, user_id: str, pixel_count: int = 1) -> bool:
        current_time = time.time()
        
        if user_id not in self.buckets:
            self.buckets[user_id] = TokenBucket(
                capacity=self.burst_capacity,
                refill_rate=self.refill_rate,
                tokens=self.burst_capacity,
                last_refill=current_time
            )
        
        bucket = self.buckets[user_id]
        
        # Refill tokens based on time elapsed
        time_elapsed = current_time - bucket.last_refill
        bucket.tokens = min(
            bucket.capacity,
            bucket.tokens + time_elapsed * bucket.refill_rate
        )
        bucket.last_refill = current_time
        
        # Check if enough tokens available
        if bucket.tokens >= pixel_count:
            bucket.tokens -= pixel_count
            return True
        
        return False
    
    async def get_remaining_tokens(self, user_id: str) -> int:
        if user_id not in self.buckets:
            return self.burst_capacity
        
        bucket = self.buckets[user_id]
        current_time = time.time()
        
        # Refill tokens based on time elapsed
        time_elapsed = current_time - bucket.last_refill
        bucket.tokens = min(
            bucket.capacity,
            bucket.tokens + time_elapsed * bucket.refill_rate
        )
        bucket.last_refill = current_time
        
        return int(bucket.tokens)
    
    def cleanup_old_buckets(self):
        current_time = time.time()
        expired_users = [
            user_id for user_id, bucket in self.buckets.items()
            if current_time - bucket.last_refill > 300  # 5 minutes
        ]
        for user_id in expired_users:
            del self.buckets[user_id]


class RedisRateLimiter:
    def __init__(self):
        self.window = 60  # 1 minute window
        self.max_pixels = 100  # Max 100 pixels per minute
    
    async def check_rate_limit(self, user_id: str, pixel_count: int = 1) -> bool:
        try:
            current_count = redis_cache.increment_pixel_count(user_id, self.window)
            return current_count <= self.max_pixels
        except Exception:
            return True  # Fail open if Redis is unavailable
    
    async def get_remaining_pixels(self, user_id: str) -> int:
        try:
            current_count = redis_cache.get_pixel_count(user_id)
            return max(0, self.max_pixels - current_count)
        except Exception:
            return self.max_pixels


ws_rate_limiter = WebSocketRateLimiter()
redis_rate_limiter = RedisRateLimiter()


async def check_pixel_rate_limit(user_id: str, pixel_count: int = 1) -> tuple[bool, str]:
    # Check in-memory token bucket for immediate rate limiting
    if not await ws_rate_limiter.check_rate_limit(user_id, pixel_count):
        remaining = await ws_rate_limiter.get_remaining_tokens(user_id)
        return False, f"Rate limit exceeded. {remaining} tokens remaining."
    
    # Check Redis for longer-term rate limiting
    if not await redis_rate_limiter.check_rate_limit(user_id, pixel_count):
        remaining = await redis_rate_limiter.get_remaining_pixels(user_id)
        return False, f"Minute rate limit exceeded. {remaining} pixels remaining."
    
    return True, "Rate limit OK."
