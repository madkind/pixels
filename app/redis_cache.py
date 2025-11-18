import os
import json
import redis
import pickle
from typing import Optional, List, Dict, Any
from datetime import datetime

from .models import CanvasState, RegionLock


class RedisCache:
    def __init__(self):
        self.is_local = os.getenv("REDIS_LOCAL", "false").lower() == "true"
        
        if self.is_local:
            self.redis_client = redis.Redis(
                host="localhost",
                port=6379,
                decode_responses=False
            )
        else:
            self.redis_client = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", 6379)),
                password=os.getenv("REDIS_PASSWORD"),
                decode_responses=False
            )
    
    def get_canvas_state(self) -> Optional[CanvasState]:
        try:
            data = self.redis_client.get("canvas:state")
            if data:
                return pickle.loads(data)
        except Exception:
            pass
        return None
    
    def set_canvas_state(self, canvas_state: CanvasState, ttl: int = 3600) -> None:
        try:
            self.redis_client.setex(
                "canvas:state", 
                ttl, 
                pickle.dumps(canvas_state)
            )
        except Exception:
            pass
    
    def get_region_locks(self) -> List[RegionLock]:
        try:
            data = self.redis_client.get("canvas:locks")
            if data:
                return pickle.loads(data)
        except Exception:
            pass
        return []
    
    def set_region_locks(self, locks: List[RegionLock], ttl: int = 300) -> None:
        try:
            self.redis_client.setex(
                "canvas:locks",
                ttl,
                pickle.dumps(locks)
            )
        except Exception:
            pass
    
    def publish_pixel_update(self, update_data: Dict[str, Any]) -> None:
        try:
            message = {
                "type": "pixel:update",
                "data": update_data,
                "timestamp": datetime.utcnow().isoformat()
            }
            self.redis_client.publish("canvas:updates", json.dumps(message))
        except Exception:
            pass
    
    def subscribe_to_updates(self):
        try:
            pubsub = self.redis_client.pubsub()
            pubsub.subscribe("canvas:updates")
            return pubsub
        except Exception:
            return None
    
    def increment_pixel_count(self, user_id: str, window: int = 60) -> int:
        try:
            key = f"rate_limit:pixels:{user_id}"
            count = self.redis_client.incr(key)
            if count == 1:
                self.redis_client.expire(key, window)
            return count
        except Exception:
            return 0
    
    def get_pixel_count(self, user_id: str) -> int:
        try:
            key = f"rate_limit:pixels:{user_id}"
            return int(self.redis_client.get(key) or 0)
        except Exception:
            return 0


redis_cache = RedisCache()
