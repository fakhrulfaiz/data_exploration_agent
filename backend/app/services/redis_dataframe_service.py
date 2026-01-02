"""
Redis DataFrame Service for storing and retrieving pandas DataFrames.
Handles serialization, deserialization, and lifecycle management of DataFrames in Redis.
"""

import pickle
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import pandas as pd
from app.services.redis_service import RedisService

logger = logging.getLogger(__name__)

class RedisDataFrameService(RedisService):
    """Service for managing pandas DataFrames in Redis with automatic cleanup and TTL"""
    
    def __init__(self):
        """Initialize Redis DataFrame service from settings"""
        # Initialize base Redis service
        super().__init__()
    
    def _generate_key(self, prefix: str = "df") -> str:
        """Generate a unique Redis key for DataFrame storage"""
        return f"{prefix}:{uuid.uuid4().hex}"
    
    def store_dataframe(
        self, 
        df: pd.DataFrame, 
        sql_query: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        try:
            # Generate unique key
            df_id = self._generate_key()
            
            # Serialize DataFrame using pickle
            df_bytes = pickle.dumps(df)
            
            # Store DataFrame with TTL
            self.redis.setex(df_id, self.ttl, df_bytes)
            
            # Create metadata
            now = datetime.utcnow()
            expires_at = now + timedelta(seconds=self.ttl)
            
            context = {
                "df_id": df_id,
                "sql_query": sql_query,
                "columns": df.columns.tolist(),
                "shape": df.shape,
                "created_at": now,
                "expires_at": expires_at,
                "metadata": metadata or {}
            }
            
            # Store metadata separately for quick access
            metadata_key = f"{df_id}:meta"
            metadata_bytes = pickle.dumps(context)
            self.redis.setex(metadata_key, self.ttl, metadata_bytes)
            
            logger.info(f"Stored DataFrame {df_id} with shape {df.shape}, expires at {expires_at}")
            return context
            
        except Exception as e:
            logger.error(f"Failed to store DataFrame: {str(e)}")
            raise RuntimeError(f"Failed to store DataFrame in Redis: {str(e)}")
    
    def get_dataframe(self, df_id: str) -> Optional[pd.DataFrame]:
        try:
            df_bytes = self.redis.get(df_id)
            if df_bytes is None:
                logger.warning(f"DataFrame {df_id} not found or expired")
                return None
            
            df = pickle.loads(df_bytes)
            logger.info(f"Retrieved DataFrame {df_id} with shape {df.shape}")
            return df
            
        except Exception as e:
            logger.error(f"Failed to retrieve DataFrame {df_id}: {str(e)}")
            return None
    
    def get_metadata(self, df_id: str) -> Optional[Dict[str, Any]]:

        try:
            metadata_key = f"{df_id}:meta"
            metadata_bytes = self.redis.get(metadata_key)
            if metadata_bytes is None:
                logger.warning(f"Metadata for DataFrame {df_id} not found or expired")
                return None
            
            metadata = pickle.loads(metadata_bytes)
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to retrieve metadata for DataFrame {df_id}: {str(e)}")
            return None
    
    def exists(self, df_id: str) -> bool:
        try:
            return self.redis.exists(df_id) > 0
        except Exception as e:
            logger.error(f"Failed to check existence of DataFrame {df_id}: {str(e)}")
            return False
    
    def delete_dataframe(self, df_id: str) -> bool:
        try:
            metadata_key = f"{df_id}:meta"
            
            # Delete both DataFrame and metadata
            deleted_count = self.redis.delete(df_id, metadata_key)
            
            if deleted_count > 0:
                logger.info(f"Deleted DataFrame {df_id} and metadata")
                return True
            else:
                logger.warning(f"DataFrame {df_id} was not found for deletion")
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete DataFrame {df_id}: {str(e)}")
            return False
    
    def extend_ttl(self, df_id: str, additional_seconds: int = None) -> bool:
    
        try:
            ttl_seconds = additional_seconds or self.ttl
            metadata_key = f"{df_id}:meta"
            
            # Extend TTL for both DataFrame and metadata
            df_result = self.redis.expire(df_id, ttl_seconds)
            meta_result = self.redis.expire(metadata_key, ttl_seconds)
            
            if df_result and meta_result:
                logger.info(f"Extended TTL for DataFrame {df_id} by {ttl_seconds}s")
                return True
            else:
                logger.warning(f"Failed to extend TTL for DataFrame {df_id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to extend TTL for DataFrame {df_id}: {str(e)}")
            return False
    
    def list_dataframes(self) -> List[Dict[str, Any]]:
        try:
            # Find all DataFrame keys
            df_keys = self.redis.keys("df:*")
            # Filter out metadata keys
            df_keys = [key.decode() for key in df_keys if not key.decode().endswith(":meta")]
            
            dataframes = []
            for df_id in df_keys:
                metadata = self.get_metadata(df_id)
                if metadata:
                    dataframes.append(metadata)
            
            logger.info(f"Found {len(dataframes)} stored DataFrames")
            return dataframes
            
        except Exception as e:
            logger.error(f"Failed to list DataFrames: {str(e)}")
            return []
    
    def cleanup_expired(self) -> int:
        try:
            # Get all DataFrame keys
            all_keys = self.redis.keys("df:*")
            existing_count = len([key for key in all_keys if not key.decode().endswith(":meta")]) // 2
            
            # Redis automatically handles TTL cleanup, but we can check what's still there
            active_dataframes = self.list_dataframes()
            active_count = len(active_dataframes)
            
            cleaned_count = max(0, existing_count - active_count)
            if cleaned_count > 0:
                logger.info(f"Redis TTL cleanup: {cleaned_count} DataFrames expired")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Failed to check cleanup status: {str(e)}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get Redis DataFrame service statistics
        
        Returns:
            Dict with service statistics
        """
        try:
            active_dataframes = self.list_dataframes()
            
            stats = {
                "active_dataframes": len(active_dataframes),
                "default_ttl": self.ttl,
                "redis_info": {
                    "host": settings.redis_host,
                    "port": settings.redis_port,
                    "db": settings.redis_db
                }
            }
            
            if active_dataframes:
                total_rows = sum(df["shape"][0] for df in active_dataframes)
                total_cols = sum(df["shape"][1] for df in active_dataframes)
                stats["total_rows"] = total_rows
                stats["total_columns"] = total_cols
                stats["oldest_dataframe"] = min(df["created_at"] for df in active_dataframes)
                stats["newest_dataframe"] = max(df["created_at"] for df in active_dataframes)
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get stats: {str(e)}")
            return {"error": str(e)}


# Global instance
_redis_df_service: Optional[RedisDataFrameService] = None


def get_redis_dataframe_service() -> RedisDataFrameService:
    """Get or create the global Redis DataFrame service instance"""
    global _redis_df_service
    
    if _redis_df_service is None:
        _redis_df_service = RedisDataFrameService()
    
    return _redis_df_service

