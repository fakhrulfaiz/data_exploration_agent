"""Base Redis service with common operations"""
import redis
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisService:
 
    def __init__(self, default_ttl: int = None):
        """Initialize Redis client"""
        if settings.redis_url:
            self.redis = redis.from_url(
                settings.redis_url,
                decode_responses=False,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
                retry_on_timeout=True
            )
        else:
            self.redis = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password if settings.redis_password else None,
                decode_responses=False,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
                retry_on_timeout=True
            )
        
        self.ttl = default_ttl or settings.redis_ttl
        logger.info(f"Initialized {self.__class__.__name__} with TTL: {self.ttl}s")
    
    def exists(self, key: str) -> bool:
        try:
            return self.redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Failed to check existence of {key}: {e}")
            return False
    
    def extend_ttl(self, key: str, seconds: int = None) -> bool:
        try:
            ttl_seconds = seconds or self.ttl
            result = self.redis.expire(key, ttl_seconds)
            if result:
                logger.debug(f"Extended TTL for {key} by {ttl_seconds}s")
            return result
        except Exception as e:
            logger.error(f"Failed to extend TTL for {key}: {e}")
            return False
    
    def delete(self, *keys: str) -> int:
        try:
            count = self.redis.delete(*keys)
            if count > 0:
                logger.debug(f"Deleted {count} key(s)")
            return count
        except Exception as e:
            logger.error(f"Failed to delete keys: {e}")
            return 0
    
    def get(self, key: str) -> Optional[bytes]:
        try:
            return self.redis.get(key)
        except Exception as e:
            logger.error(f"Failed to get {key}: {e}")
            return None
    
    def set(self, key: str, value: bytes, ttl: int = None) -> bool:
        try:
            ttl_seconds = ttl or self.ttl
            self.redis.setex(key, ttl_seconds, value)
            return True
        except Exception as e:
            logger.error(f"Failed to set {key}: {e}")
            return False
