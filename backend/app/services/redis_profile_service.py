import pickle
import logging
from typing import Optional, Dict, Any
from app.services.redis_service import RedisService

logger = logging.getLogger(__name__)


class RedisProfileService(RedisService):
    def __init__(self, cache_ttl: int = 1800):
        super().__init__(default_ttl=cache_ttl)
    
    def store_preferences(self, user_id: str, profile: Dict[str, Any]) -> bool:
        try:
            key = f"user_prefs:{user_id}"
            prefs_bytes = pickle.dumps(profile)
            result = self.set(key, prefs_bytes)
            if result:
                logger.info(f"Cached preferences for user {user_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to cache preferences for {user_id}: {e}")
            return False
    
    def get_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            key = f"user_prefs:{user_id}"
            prefs_bytes = self.get(key)
            if prefs_bytes:
                return pickle.loads(prefs_bytes)
            return None
        except Exception as e:
            logger.error(f"Failed to get preferences for {user_id}: {e}")
            return None
    
    def invalidate_preferences(self, user_id: str) -> bool:
        try:
            key = f"user_prefs:{user_id}"
            count = self.delete(key)
            if count > 0:
                logger.info(f"Invalidated preferences cache for user {user_id}")
            return count > 0
        except Exception as e:
            logger.error(f"Failed to invalidate preferences for {user_id}: {e}")
            return False


# Global instance
_redis_profile_service: Optional[RedisProfileService] = None


def get_redis_profile_service() -> RedisProfileService:
    global _redis_profile_service
    if _redis_profile_service is None:
        _redis_profile_service = RedisProfileService()
    return _redis_profile_service
